from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QObject, QProcess, Signal
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene

from chemunited.simulation import playback_export
from chemunited.simulation.playback_export import (
    FPS,
    PlaybackExporter,
    PlaybackExportOptions,
    PlaybackFrameSchedule,
    render_playback_frame,
)
from chemunited.simulation.playback_export_dialog import PlaybackExportDialog


@pytest.mark.parametrize(
    "times,speed,moving,expected",
    [
        ([4, 4.0625, 4.125, 4.1875], 2.5, 2, [4, 4.125]),
        ([8, 8.125, 8.25], 2.5, 2, [8, 8.125]),
        ([3, 4, 8], 10, 10, [3, 3, 4, 4, 4, 4, 4, 4, 4, 4]),
        ([42], 1, 0, []),
        ([2, 2.125], 0.125, 20, [2] * 20),
    ],
)
def test_frame_schedule_preserves_recorded_timing(times, speed, moving, expected):
    schedule = PlaybackFrameSchedule(times, speed)
    assert schedule.moving_frames == moving
    assert [schedule.snapshot_time(i) for i in range(moving)] == expected
    assert [schedule.snapshot_time(i) for i in range(moving, schedule.frame_count)] == [
        times[-1]
    ] * FPS
    assert schedule.duration == schedule.frame_count / FPS


@pytest.mark.parametrize(
    "times,speed", [([], 1), ([1, 1], 1), ([float("nan")], 1), ([1], 0)]
)
def test_invalid_schedule_is_rejected(times, speed):
    with pytest.raises(ValueError):
        PlaybackFrameSchedule(times, speed)


def test_dialog_defaults_and_estimated_duration(qtbot, tmp_path):
    dialog = PlaybackExportDialog([4, 14])
    qtbot.addWidget(dialog)
    assert dialog.options(tmp_path / "run.mp4") == PlaybackExportOptions(
        tmp_path / "run.mp4"
    )
    assert "11.00 s" in dialog.duration_label.text()
    dialog.speed_spin.setValue(2)
    assert "6.00 s" in dialog.duration_label.text()
    dialog.format_combo.setCurrentIndex(1)
    assert dialog.selected_format == "gif"


class _Playback:
    def __init__(self, item):
        self.times = [4.0, 4.1]
        self.item = item
        self.applied = []

    def apply_at_time(self, t, components, connections, *, strict=False):
        assert strict
        self.applied.append(t)
        self.item.setBrush(QColor("red" if t == self.times[0] else "blue"))


@pytest.fixture
def platform(qtbot):
    scene = QGraphicsScene()
    scene.setBackgroundBrush(QColor("white"))
    item = scene.addRect(0, 0, 100, 50, brush=QColor("red"))
    item.setFlag(QGraphicsItem.ItemIsSelectable, True)
    item.setSelected(True)
    return scene, item, _Playback(item)


class _Process(QObject):
    """An encoder that only consumes bytes when the test explicitly drains it."""

    started = Signal()
    bytesWritten = Signal(int)
    readyReadStandardError = Signal()
    readyReadStandardOutput = Signal()
    errorOccurred = Signal(object)
    finished = Signal(int, object)
    Running, NotRunning = QProcess.Running, QProcess.NotRunning
    NormalExit, CrashExit = QProcess.NormalExit, QProcess.CrashExit
    FailedToStart = QProcess.FailedToStart
    ProcessState, ExitStatus = QProcess.ProcessState, QProcess.ExitStatus
    created = []
    fail_start = False

    def __init__(self, parent):
        super().__init__(parent)
        self.created.append(self)
        self._state = self.NotRunning
        self.buffered = 0
        self.peak = 0
        self.accept_limit = None
        self.accepted = bytearray()
        self.closed = 0

    def start(self, program, args):
        self.args = args
        if self.fail_start:
            self.errorOccurred.emit(self.FailedToStart)
        else:
            self._state = self.Running
            self.started.emit()

    def state(self):
        return self._state

    def bytesToWrite(self):
        return self.buffered

    def write(self, data):
        count = (
            len(data)
            if self.accept_limit is None
            else min(len(data), self.accept_limit)
        )
        if count >= 0:
            self.buffered += count
            self.peak = max(self.peak, self.buffered)
            self.accepted.extend(data[:count])
        return count

    def drain(self):
        count, self.buffered = self.buffered, 0
        self.bytesWritten.emit(count)

    def closeWriteChannel(self):
        self.closed += 1

    def readAllStandardError(self):
        return b""

    def readAllStandardOutput(self):
        return b""

    def errorString(self):
        return "injected encoder failure"

    def kill(self):
        self._state = self.NotRunning
        self.errorOccurred.emit(QProcess.Crashed)
        self.finished.emit(9, self.CrashExit)

    def finish(self, code=0):
        self._state = self.NotRunning
        if code == 0:
            Path(self.args[-1]).write_bytes(b"encoded")
        self.finished.emit(code, self.NormalExit)


@pytest.fixture
def fake_encoder(monkeypatch):
    _Process.created = []
    _Process.fail_start = False
    monkeypatch.setattr(playback_export, "QProcess", _Process)
    monkeypatch.setattr(playback_export, "get_ffmpeg_exe", lambda: "ffmpeg")
    return _Process


def _job(platform, destination):
    scene, item, playback = platform
    job = PlaybackExporter(playback, scene, {}, {})
    results = {"completed": [], "failed": [], "cancelled": []}
    job.completed.connect(results["completed"].append)
    job.failed.connect(results["failed"].append)
    job.cancelled.connect(lambda: results["cancelled"].append(True))
    options = PlaybackExportOptions(destination, destination.suffix[1:], 160, 90)
    return job, options, results


def _feed(job):
    while not job._input_closed:
        job._pump()
        job._process.drain()


def test_backpressure_partial_writes_and_success_wait_for_exit(
    platform, tmp_path, fake_encoder
):
    job, options, results = _job(platform, tmp_path / "run.mp4")
    job.start(options)
    process = job._process
    size = options.width * options.height * 4
    process.accept_limit = size // 2
    job._pump()
    assert job._frame == 0
    job._pump()
    assert job._frame == 1
    for _ in range(20):
        job._pump()
    assert process.buffered == process.peak == size * 2
    assert job._frame == 2
    process.drain()
    _feed(job)
    assert process.closed == 1
    assert process.peak <= size * 2
    assert len(process.accepted) == job.schedule.frame_count * size
    assert platform[2].applied == platform[2].times
    assert not results["completed"]
    assert not options.destination.exists()
    process.finish()
    assert results == {
        "completed": [str(options.destination)],
        "failed": [],
        "cancelled": [],
    }
    assert platform[1].isSelected()
    assert not list(tmp_path.glob(".playback-export-*"))


@pytest.mark.parametrize("failure", ["startup", "write", "exit", "render", "cancel"])
def test_failures_and_cancellation_preserve_destination(
    platform, tmp_path, fake_encoder, monkeypatch, failure
):
    destination = tmp_path / "run.mp4"
    destination.write_bytes(b"original")
    job, options, results = _job(platform, destination)
    if failure == "startup":
        fake_encoder.fail_start = True
    job.start(options)
    if failure == "write":
        job._process.accept_limit = -1
        job._pump()
    elif failure == "exit":
        job._pump()
        job._process.finish(1)
    elif failure == "render":

        def fail(*args, **kwargs):
            raise RuntimeError("unreadable snapshot")

        monkeypatch.setattr(platform[2], "apply_at_time", fail)
        job._pump()
    elif failure == "cancel":
        job._pump()
        job.cancel()
    assert not job.active
    assert len(results["cancelled"] if failure == "cancel" else results["failed"]) == 1
    assert not results["completed"]
    job._pump()  # queued callbacks after cancellation must be harmless
    assert destination.read_bytes() == b"original"
    assert platform[1].isSelected()
    assert not list(tmp_path.glob(".playback-export-*"))


@pytest.mark.parametrize("stage", ["render", "palette", "gif"])
def test_cancel_each_gif_stage_does_not_launch_another(
    platform, tmp_path, fake_encoder, stage
):
    job, options, results = _job(platform, tmp_path / "run.gif")
    job.start(options)
    if stage != "render":
        _feed(job)
        job._process.finish()
    if stage == "gif":
        job._process.finish()
    assert job._stage == stage
    count = len(fake_encoder.created)
    job.cancel()
    assert len(fake_encoder.created) == count
    assert results["cancelled"] == [True]
    assert not list(tmp_path.glob(".playback-export-*"))


def test_missing_destination_directory_is_reported(platform, tmp_path, fake_encoder):
    job, options, results = _job(platform, tmp_path / "missing" / "run.mp4")
    job.start(options)
    assert len(results["failed"]) == 1
    assert not fake_encoder.created
    assert platform[1].isSelected()


def test_commit_error_preserves_existing_destination(
    platform, tmp_path, fake_encoder, monkeypatch
):
    destination = tmp_path / "run.mp4"
    destination.write_bytes(b"original")
    job, options, results = _job(platform, destination)

    def denied(*args):
        raise PermissionError("Destination is locked")

    monkeypatch.setattr(playback_export.os, "replace", denied)
    job.start(options)
    _feed(job)
    job._process.finish()
    assert "locked" in results["failed"][0]
    assert destination.read_bytes() == b"original"
    assert not list(tmp_path.glob(".playback-export-*"))


def test_encoder_diagnostics_are_drained_and_bounded(
    platform, tmp_path, fake_encoder, monkeypatch
):
    job, options, results = _job(platform, tmp_path / "run.mp4")
    job.start(options)
    monkeypatch.setattr(job._process, "readAllStandardError", lambda: b"x" * 100_000)
    job._process.readyReadStandardError.emit()
    assert len(job._diagnostics) == 16_384
    job._process.finish(1)
    assert len(results["failed"]) == 1
    assert len(results["failed"][0]) < 17_000


def test_frame_render_is_opaque_rgba_and_preserves_framing(platform, tmp_path):
    scene, item, _ = platform
    options = PlaybackExportOptions(tmp_path / "run.mp4", width=160, height=90)
    image = render_playback_frame(scene, scene.itemsBoundingRect(), options, 4, 9)
    assert image.format() == QImage.Format_RGBA8888
    assert image.pixelColor(44, 24) == QColor("red")
    assert image.pixelColor(159, 89).alpha() == 255
    # RGBA bytes must retain red/blue channel order at the encoder boundary.
    offset = 24 * image.bytesPerLine() + 44 * 4
    assert image.constBits()[: image.sizeInBytes()][offset : offset + 4] == bytes(
        (255, 0, 0, 255)
    )


@pytest.mark.parametrize("format", ["mp4", "gif"])
def test_real_encoding_decodes_first_and_final_state(qtbot, platform, tmp_path, format):
    job, options, results = _job(platform, tmp_path / f"real output.{format}")
    job.start(options)
    qtbot.waitUntil(lambda: not job.active, timeout=30000)
    assert not results["failed"], results
    assert results["completed"] == [str(options.destination)]
    # Use the packaged binary for decoding too; ffprobe is not required.
    import imageio_ffmpeg

    frames = imageio_ffmpeg.read_frames(str(options.destination), pix_fmt="rgb24")
    try:
        metadata = next(frames)
        decoded = list(frames)
    finally:
        frames.close()
    assert metadata["size"] == (160, 90)
    assert metadata["fps"] == pytest.approx(FPS)
    assert metadata["duration"] == pytest.approx(job.schedule.duration, abs=0.06)
    assert len(decoded) >= FPS
    offset = (24 * options.width + 44) * 3
    first = decoded[0][offset : offset + 3]
    assert first[0] > 220 and first[2] < 35
    for frame in decoded[-FPS:]:
        final = frame[offset : offset + 3]
        assert final[2] > 220 and final[0] < 35
    if format == "mp4":
        assert len(decoded) == job.schedule.frame_count
    else:
        assert b"NETSCAPE2.0" in options.destination.read_bytes()
    assert not list(tmp_path.glob(".playback-export-*"))
