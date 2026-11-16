"""Bounded, asynchronous export of recorded platform states using Qt and FFmpeg."""

from __future__ import annotations

import bisect
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from imageio_ffmpeg import get_ffmpeg_exe
from loguru import logger
from PyQt5 import sip
from PyQt5.QtCore import QObject, QProcess, QRectF, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QImage, QPainter
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsScene

from chemunited.elements.access import Components, Connections
from chemunited.project.platform_svg import _export_rect, _visible_edit_handles

from .playback import SimulationPlayback

FPS = 20
_DIAGNOSTIC_LIMIT = 16_384


@dataclass(frozen=True)
class PlaybackExportOptions:
    destination: Path
    format: Literal["mp4", "gif"] = "mp4"
    width: int = 1280
    height: int = 720
    speed: float = 1.0

    def __post_init__(self) -> None:
        if self.format not in ("mp4", "gif"):
            raise ValueError("Choose MP4 or GIF.")
        if self.destination.suffix.lower() != f".{self.format}":
            raise ValueError(f"The destination must end in .{self.format}.")
        if self.width < 2 or self.height < 64 or self.width % 2 or self.height % 2:
            raise ValueError("Export dimensions must be even and at least 2 × 64.")
        if not math.isfinite(self.speed) or not 0.1 <= self.speed <= 1000:
            raise ValueError("Playback speed must be between 0.1 and 1000×.")


class PlaybackFrameSchedule:
    """Map constant-rate video frames to exact, possibly irregular snapshots."""

    def __init__(self, times: Sequence[float], speed: float) -> None:
        self.times = tuple(times)
        if not self.times or any(not math.isfinite(t) for t in self.times):
            raise ValueError("The recording has no valid snapshots to export.")
        if any(a >= b for a, b in zip(self.times, self.times[1:])):
            raise ValueError("Recorded timestamps must be strictly increasing.")
        if not math.isfinite(speed) or not 0.1 <= speed <= 1000:
            raise ValueError("Playback speed must be between 0.1 and 1000×.")
        self.speed = speed
        self.moving_frames = math.ceil((self.times[-1] - self.times[0]) * FPS / speed)
        self.frame_count = self.moving_frames + FPS

    @property
    def duration(self) -> float:
        return self.frame_count / FPS

    def snapshot_time(self, frame: int) -> float:
        if not 0 <= frame < self.frame_count:
            raise IndexError(frame)
        if frame >= self.moving_frames:
            return self.times[-1]
        sample = self.times[0] + frame * self.speed / FPS
        return self.times[max(0, bisect.bisect_right(self.times, sample) - 1)]


def render_playback_frame(
    scene: QGraphicsScene,
    bounds: QRectF,
    options: PlaybackExportOptions,
    timestamp: float,
    last_time: float,
) -> QImage:
    """Render scene content, including live parts, without view chrome or grid."""
    image = QImage(options.width, options.height, QImage.Format_RGBA8888)
    if image.isNull():
        raise MemoryError("Could not allocate the export frame.")
    background = scene.backgroundBrush().color()
    if not background.isValid() or background.alpha() == 0:
        background = QColor("white")
    background.setAlpha(255)
    image.fill(background)
    painter = QPainter(image)
    try:
        painter.setRenderHints(
            QPainter.Antialiasing
            | QPainter.TextAntialiasing
            | QPainter.SmoothPixmapTransform
        )
        footer = max(32, options.height // 15)
        scene.render(
            painter,
            QRectF(0, 0, options.width, options.height - footer),
            bounds,
            Qt.AspectRatioMode.KeepAspectRatio,
        )
        painter.setPen(QColor("white" if background.lightness() < 128 else "#202020"))
        font = QFont()
        font.setPixelSize(max(12, options.height // 45))
        painter.setFont(font)
        painter.drawText(
            QRectF(12, options.height - footer, options.width - 24, footer),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"t = {timestamp:g} s / {last_time:g} s",
        )
    finally:
        painter.end()
    return image


class PlaybackExporter(QObject):
    """One export job. All Qt/SQLite access stays on the GUI thread.

    QProcess buffers at most two RGBA frames. FFmpeg encodes independently;
    frame production is scheduled by bytesWritten instead of blocking writes.
    """

    progress = pyqtSignal(int, str)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(
        self,
        playback: SimulationPlayback,
        scene: QGraphicsScene,
        components: Components,
        connections: Connections,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.playback = playback
        self.scene = scene
        self.components = components
        self.connections = connections
        self._active = False
        self._started = False
        self._cancel_requested = False
        self._error = ""
        self._process: QProcess | None = None
        self._temp_dir: tempfile.TemporaryDirectory | None = None
        self._selected_items: tuple[QGraphicsItem, ...] = ()
        self._hidden_handles: tuple[QGraphicsItem, ...] = ()
        self._diagnostics = b""
        self._stage = ""
        self._frame = 0
        self._cached_time: float | None = None
        self._cached_bytes = b""
        self._pending_bytes = b""
        self._input_closed = False
        self._pump_timer = QTimer(self)
        self._pump_timer.setSingleShot(True)
        self._pump_timer.timeout.connect(self._pump)

    @property
    def active(self) -> bool:
        return self._active

    def start(self, options: PlaybackExportOptions) -> None:
        if self._started:
            raise RuntimeError("Create a new exporter for each job.")
        self._started = self._active = True
        self.options = options
        try:
            self.schedule = PlaybackFrameSchedule(self.playback.times, options.speed)
            self._executable = get_ffmpeg_exe()
            self._temp_dir = tempfile.TemporaryDirectory(
                prefix=".playback-export-", dir=options.destination.parent
            )
            self._work_dir = Path(self._temp_dir.name)
            self._output = self._work_dir / f"animation.{options.format}"
            self._selected_items = tuple(self.scene.selectedItems())
            self._hidden_handles = _visible_edit_handles(self.scene)
            self.scene.clearSelection()
            for item in self._hidden_handles:
                item.hide()
            self._bounds = _export_rect(self.scene)
            self._frame_bytes = options.width * options.height * 4
            args = [
                "-f",
                "rawvideo",
                "-pixel_format",
                "rgba",
                "-video_size",
                f"{options.width}x{options.height}",
                "-framerate",
                str(FPS),
                "-i",
                "pipe:0",
                "-an",
            ]
            if options.format == "mp4":
                args += [
                    "-c:v",
                    "libx264",
                    "-crf",
                    "18",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(self._output),
                ]
            else:
                args += [
                    "-c:v",
                    "ffv1",
                    "-pix_fmt",
                    "bgr0",
                    str(self._work_dir / "frames.mkv"),
                ]
            self.progress.emit(0, "Rendering playback…")
            self._launch("render", args)
        except Exception as exc:
            self._fail(str(exc))

    def _launch(self, stage: str, args: list[str]) -> None:
        self._stage = stage
        self._diagnostics = b""
        process = QProcess(self)
        self._process = process
        process.started.connect(self._schedule_pump)
        process.bytesWritten.connect(self._schedule_pump)
        process.readyReadStandardError.connect(lambda: self._read_stderr(process))
        process.readyReadStandardOutput.connect(lambda: self._discard_stdout(process))
        process.errorOccurred.connect(lambda error: self._on_error(process, error))
        process.finished.connect(
            lambda code, status: self._on_finished(process, code, status)
        )
        process.start(
            self._executable, ["-hide_banner", "-loglevel", "error", "-y", *args]
        )

    def _read_stderr(self, process: QProcess) -> None:
        data = bytes(process.readAllStandardError())
        if process is self._process:
            self._diagnostics = (self._diagnostics + data)[-_DIAGNOSTIC_LIMIT:]

    def _discard_stdout(self, process: QProcess) -> None:
        process.readAllStandardOutput()

    def _schedule_pump(self, *_args) -> None:
        if (
            self._active
            and not self._cancel_requested
            and not self._error
            and self._stage == "render"
            and not self._input_closed
            and not self._pump_timer.isActive()
        ):
            self._pump_timer.start(0)

    def _pump(self) -> None:
        process = self._process
        if (
            not self._active
            or self._cancel_requested
            or self._error
            or self._stage != "render"
            or self._input_closed
            or process is None
            or process.state() != QProcess.ProcessState.Running
        ):
            return
        try:
            # Check capacity before rendering/queuing another full frame.
            next_size = len(self._pending_bytes) or self._frame_bytes
            if process.bytesToWrite() + next_size > 2 * self._frame_bytes:
                return
            if not self._pending_bytes:
                t = self.schedule.snapshot_time(self._frame)
                if t != self._cached_time:
                    self.playback.apply_at_time(
                        t, self.components, self.connections, strict=True
                    )
                    image = render_playback_frame(
                        self.scene,
                        self._bounds,
                        self.options,
                        t,
                        self.schedule.times[-1],
                    )
                    bits = image.constBits()
                    if bits is None:
                        raise MemoryError("Could not read the export frame.")
                    self._cached_bytes = bits.asstring(image.sizeInBytes())
                    self._cached_time = t
                self._pending_bytes = self._cached_bytes
            written = process.write(self._pending_bytes)
            if written < 0:
                raise OSError("Could not write the playback frame to FFmpeg.")
            self._pending_bytes = self._pending_bytes[written:]
            if not self._pending_bytes:
                self._frame += 1
                ceiling = 70 if self.options.format == "gif" else 95
                self.progress.emit(
                    self._frame * ceiling // self.schedule.frame_count,
                    f"Rendering frame {self._frame} / {self.schedule.frame_count}…",
                )
            if self._frame == self.schedule.frame_count:
                self._input_closed = True
                process.closeWriteChannel()  # drains queued bytes before EOF
                self.progress.emit(ceiling, "Finishing video encoding…")
            elif written:
                self._schedule_pump()
        except Exception as exc:
            self._fail(str(exc))

    def cancel(self) -> None:
        if not self._active:
            return
        self._cancel_requested = True
        self._stop_process()

    def _fail(self, message: str) -> None:
        if not self._active:
            return
        self._error = message or "Playback export failed."
        self._stop_process()

    def _stop_process(self) -> None:
        self._pump_timer.stop()
        if (
            self._process is not None
            and self._process.state() != QProcess.ProcessState.NotRunning
        ):
            self._process.kill()
        else:
            self._finish()

    def _on_error(self, process: QProcess, error: QProcess.ProcessError) -> None:
        if process is not self._process or not self._active:
            return
        if self._cancel_requested or self._error:
            if process.state() == QProcess.ProcessState.NotRunning:
                self._finish()
            return
        self._read_stderr(process)
        self._fail(f"FFmpeg could not encode the playback: {process.errorString()}")

    def _on_finished(
        self, process: QProcess, code: int, status: QProcess.ExitStatus
    ) -> None:
        if process is not self._process or not self._active:
            return
        self._read_stderr(process)
        if self._cancel_requested or self._error:
            self._finish()
            return
        if code != 0 or status != QProcess.ExitStatus.NormalExit:
            self._fail(f"FFmpeg failed during {self._stage} (exit code {code}).")
            return
        try:
            if self._stage == "render" and not self._input_closed:
                raise RuntimeError(
                    "FFmpeg exited before all playback frames were written."
                )
            if self.options.format == "gif" and self._stage == "render":
                self.progress.emit(70, "Building GIF palette…")
                self._launch(
                    "palette",
                    [
                        "-i",
                        str(self._work_dir / "frames.mkv"),
                        "-vf",
                        "palettegen=stats_mode=full",
                        "-frames:v",
                        "1",
                        "-update",
                        "1",
                        str(self._work_dir / "palette.png"),
                    ],
                )
            elif self._stage == "palette":
                self.progress.emit(85, "Encoding GIF…")
                self._launch(
                    "gif",
                    [
                        "-i",
                        str(self._work_dir / "frames.mkv"),
                        "-i",
                        str(self._work_dir / "palette.png"),
                        "-lavfi",
                        "paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle",
                        "-loop",
                        "0",
                        str(self._output),
                    ],
                )
            else:
                if not self._output.is_file() or self._output.stat().st_size == 0:
                    raise OSError("FFmpeg did not produce an animation.")
                os.replace(self._output, self.options.destination)
                self._finish()
        except Exception as exc:
            self._fail(str(exc))
        finally:
            process.deleteLater()

    def _finish(self) -> None:
        if not self._active:
            return
        self._active = False
        self._pump_timer.stop()
        for item in self._hidden_handles:
            if not sip.isdeleted(item):
                item.show()
        for item in self._selected_items:
            if not sip.isdeleted(item):
                item.setSelected(True)
        if self._temp_dir is not None:
            try:
                self._temp_dir.cleanup()
            except OSError:
                logger.exception("Could not remove playback export temporary files")
        self._cached_bytes = self._pending_bytes = b""
        if self._cancel_requested:
            self.cancelled.emit()
        elif self._error:
            detail = self._diagnostics.decode("utf-8", errors="replace").strip()
            self.failed.emit(f"{self._error}\n{detail}" if detail else self._error)
        else:
            self.progress.emit(100, "Animation saved.")
            self.completed.emit(str(self.options.destination))
