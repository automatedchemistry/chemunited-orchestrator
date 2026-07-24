from __future__ import annotations

import json
import socket
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import requests
from chemunited_core.common.enums import PhaseKind
from chemunited_core.compounds import COMPOUNDS
from loguru import logger
from PyQt5 import sip
from PyQt5.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    IndeterminateProgressRing,
    NavigationItemPosition,
    SegmentedWidget,
    Slider,
    isDarkTheme,
)

from chemunited.shared.icon import OrchestratorIcon
from chemunited.shared.widgets.frame_base import FrameBase

from .final_state import load_edge_cells
from .graph_simulation import SimGraphicView
from .playback import SimulationPlayback

if TYPE_CHECKING:
    from chemunited.setup import SetupWindow

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SIM_SERVER_PORT = 1472
_SIM_BASE_URL = f"http://localhost:{_SIM_SERVER_PORT}"
_API_READY_TIMEOUT = 20.0
_API_POLL_INTERVAL = 1.0

_PA_TO_BAR = 1e-5
_M3S_TO_MLMIN = 6e7
_K_TO_C = -273.15

Series = dict[str, tuple[list[float], list[float]]]


# ---------------------------------------------------------------------------
# Server helpers
# ---------------------------------------------------------------------------


def _sim_server_executable() -> str:
    scripts_dir = Path(sys.executable).parent
    name = "chemunited-sim.exe" if sys.platform == "win32" else "chemunited-sim"
    return str(scripts_dir / name)


def _is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("localhost", port)) == 0


def _wait_for_api(base_url: str, timeout: float = _API_READY_TIMEOUT) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = requests.get(f"{base_url}/status", timeout=2)
            if r.status_code == 200:
                return True
        except requests.RequestException:
            pass
        time.sleep(_API_POLL_INTERVAL)
    return False


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _matches(db_key: str, name: str) -> bool:
    key = db_key.lower()
    n = name.lower()
    return key == n or key.startswith(n + ".") or key.startswith(n + "_")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# SimDbReader
# ---------------------------------------------------------------------------


class SimDbReader:
    """Read per-component time-series from a simulation SQLite DB."""

    def __init__(self, db_path: Path) -> None:
        uri = f"file:{db_path}?mode=ro"
        self._conn = sqlite3.connect(uri, uri=True)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()

    def pressure(self, component: str) -> Series:
        series: dict[str, tuple[list, list]] = defaultdict(lambda: ([], []))
        try:
            if _table_exists(self._conn, "node_pressure"):
                for row in self._conn.execute(
                    "SELECT time, node_id, pressure FROM node_pressure ORDER BY time"
                ):
                    if _matches(row["node_id"], component):
                        xs, ys = series[row["node_id"]]
                        xs.append(float(row["time"]))
                        ys.append(float(row["pressure"]) * _PA_TO_BAR)
            if _table_exists(self._conn, "inventory_state"):
                for row in self._conn.execute(
                    "SELECT time, node_id, pressure FROM inventory_state ORDER BY time"
                ):
                    if _matches(row["node_id"], component):
                        key = f"{row['node_id']} (inv)"
                        xs, ys = series[key]
                        xs.append(float(row["time"]))
                        ys.append(float(row["pressure"]) * _PA_TO_BAR)
        except sqlite3.Error as exc:
            logger.warning(f"DB error reading pressure for '{component}': {exc}")
        return {k: v for k, v in series.items() if v[0]}

    def temperature(self, component: str) -> Series:
        series: dict[str, tuple[list, list]] = defaultdict(lambda: ([], []))
        try:
            if _table_exists(self._conn, "inventory_state"):
                for row in self._conn.execute(
                    "SELECT time, node_id, temperature FROM inventory_state ORDER BY time"
                ):
                    if _matches(row["node_id"], component):
                        key = f"{row['node_id']} (inv)"
                        xs, ys = series[key]
                        xs.append(float(row["time"]))
                        ys.append(float(row["temperature"]) + _K_TO_C)
            if _table_exists(self._conn, "cell_state"):
                for row in self._conn.execute(
                    """
                    SELECT time, edge_id, AVG(temperature) AS avg_temp
                    FROM cell_state
                    GROUP BY time, edge_id
                    ORDER BY time
                """
                ):
                    if (
                        _matches(row["edge_id"], component)
                        and row["avg_temp"] is not None
                    ):
                        xs, ys = series[row["edge_id"]]
                        xs.append(float(row["time"]))
                        ys.append(float(row["avg_temp"]) + _K_TO_C)
        except sqlite3.Error as exc:
            logger.warning(f"DB error reading temperature for '{component}': {exc}")
        return {k: v for k, v in series.items() if v[0]}

    def flow(self, component: str) -> Series:
        series: dict[str, tuple[list, list]] = defaultdict(lambda: ([], []))
        try:
            if _table_exists(self._conn, "edge_flow"):
                for row in self._conn.execute(
                    "SELECT time, edge_id, flow_rate FROM edge_flow ORDER BY time"
                ):
                    if _matches(row["edge_id"], component):
                        xs, ys = series[row["edge_id"]]
                        xs.append(float(row["time"]))
                        ys.append(float(row["flow_rate"]) * _M3S_TO_MLMIN)
        except sqlite3.Error as exc:
            logger.warning(f"DB error reading flow for '{component}': {exc}")
        return {k: v for k, v in series.items() if v[0]}

    def content(self, component: str) -> Series:
        series: dict[str, tuple[list, list]] = defaultdict(lambda: ([], []))
        try:
            if _table_exists(self._conn, "inventory_content"):
                for row in self._conn.execute(
                    """
                    SELECT time, node_id, phase, species_id, moles
                    FROM inventory_content
                    WHERE species_id != '__carrier__'
                    ORDER BY time
                """
                ):
                    if _matches(row["node_id"], component):
                        key = f"{row['node_id']} / {row['phase']} / {row['species_id']}"
                        xs, ys = series[key]
                        xs.append(float(row["time"]))
                        ys.append(float(row["moles"]))
        except sqlite3.Error as exc:
            logger.warning(f"DB error reading content for '{component}': {exc}")
        return {k: v for k, v in series.items() if v[0]}

    def length_profile(self, edge_id: str, t: float) -> Series:
        """Per-(phase, species) moles vs. cumulative position (mm) along
        *edge_id*'s cells at exactly *t* - a single-time spatial snapshot,
        not a time series. Unlike the other methods above, *edge_id* is
        matched exactly (it's the primary key into edge_cells/cell_state/
        cell_content), not prefix-matched.
        """
        series: dict[str, tuple[list, list]] = defaultdict(lambda: ([], []))
        try:
            cells = load_edge_cells(self._conn, edge_id, t)
            if not cells:
                return {}

            lengths_mm: dict[int, float] = {}
            moles_by_cell: dict[int, dict[str, float]] = {}
            for cell_index, phases in cells.items():
                cell_values: dict[str, float] = {}
                length_mm = 0.0
                for phase_kind, _fraction, _temperature, length_m, species in phases:
                    length_mm = length_m * 1000.0
                    for species_id, moles in species.items():
                        key = f"{phase_kind.value} / {species_id}"
                        cell_values[key] = cell_values.get(key, 0.0) + moles
                lengths_mm[cell_index] = length_mm
                moles_by_cell[cell_index] = cell_values

            keys = {k for values in moles_by_cell.values() for k in values}
            for key in sorted(keys):
                xs, ys = series[key]
                position_mm = 0.0
                for cell_index in sorted(cells):  # 0 = origin end
                    length_mm = lengths_mm[cell_index]
                    moles = moles_by_cell[cell_index].get(key, 0.0)
                    xs.append(position_mm)
                    ys.append(moles)
                    position_mm += length_mm
                    xs.append(position_mm)
                    ys.append(moles)
        except sqlite3.Error as exc:
            logger.warning(f"DB error reading length profile for '{edge_id}': {exc}")
        return {k: v for k, v in series.items() if v[0]}


def _compound_series_style(label: str) -> tuple[str | None, float]:
    """Resolve (color, alpha) for a Content/Length-Profile series label so its
    line matches the compound's canvas color. Labels end in
    '.../phase/species_id' (see SimDbReader.content/length_profile). Falls
    back to (None, 1.0) - matplotlib's default color cycle - if the label is
    unparseable or the species isn't currently registered.
    """
    parts = label.split(" / ")
    if len(parts) < 2:
        return None, 1.0
    phase, species_id = parts[-2], parts[-1]
    if species_id not in COMPOUNDS:
        return None, 1.0
    alpha = 0.5 if phase == PhaseKind.GAS.value else 1.0
    return COMPOUNDS[species_id].rgb_hex, alpha


# ---------------------------------------------------------------------------
# SimRunWorker
# ---------------------------------------------------------------------------


class SimRunWorker(QThread):
    """Background thread that drives the full simulation pipeline."""

    status_changed = pyqtSignal(str)
    time_updated = pyqtSignal(float)
    simulation_done = pyqtSignal(str)
    simulation_failed = pyqtSignal(str)

    def __init__(self, process: str, project_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._process = process
        self._project_path = project_path
        self._session = requests.Session()
        self._session.trust_env = False
        self._session.proxies.update({"http": "", "https": ""})

    def _get(self, endpoint: str, timeout: int = 5):
        return self._session.get(f"{_SIM_BASE_URL}{endpoint}", timeout=timeout)

    def _post(self, endpoint: str, data: dict, timeout: int = 10):
        return self._session.post(
            f"{_SIM_BASE_URL}{endpoint}", json=data, timeout=timeout
        )

    def run(self) -> None:
        try:
            self._run_pipeline()
        except Exception as exc:
            logger.exception("Unexpected error in SimRunWorker")
            self.simulation_failed.emit(str(exc))

    def _run_pipeline(self) -> None:
        # 1. Ensure server is up
        self.status_changed.emit("Starting simulation server…")
        if not _is_port_in_use(_SIM_SERVER_PORT):
            exe = _sim_server_executable()
            sim_dir = self._project_path / "simulations"
            sim_dir.mkdir(parents=True, exist_ok=True)
            try:
                subprocess.Popen(  # nosec B603 # shell=False; exe resolved from sys.executable's dir, args are ints/paths
                    [
                        exe,
                        str(self._project_path),
                        "--port",
                        str(_SIM_SERVER_PORT),
                        "--db",
                        str(sim_dir),
                        "--tray",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                self.simulation_failed.emit(
                    f"chemunited-sim executable not found at: {exe}"
                )
                return
            if not _wait_for_api(_SIM_BASE_URL):
                self.simulation_failed.emit(
                    "Simulation server did not respond in time."
                )
                return
        else:
            if not _wait_for_api(_SIM_BASE_URL, timeout=5):
                self.simulation_failed.emit(
                    "Port 1472 is in use but server is not responding."
                )
                return

        # 2. Load project
        self.status_changed.emit("Loading project…")
        try:
            r = self._post("/project/load", {"path": str(self._project_path)})
            if r.status_code not in (200, 201):
                detail = r.json().get("detail", r.text) if r.content else r.text
                self.simulation_failed.emit(f"Project load failed: {detail}")
                return
        except requests.RequestException as exc:
            self.simulation_failed.emit(f"Could not reach server: {exc}")
            return

        # 3. Write temporary protocol file
        self.status_changed.emit("Preparing protocol…")
        historic_dir = self._project_path / "protocols_historic"
        historic_dir.mkdir(parents=True, exist_ok=True)
        temp_path = historic_dir / "_temp.json"
        temp_path.write_text(
            json.dumps({"main_parameter": {}, f"{self._process}_0": {}}, indent=2),
            encoding="utf-8",
        )

        # 4. Start simulation
        self.status_changed.emit("Starting simulation…")
        execution_id = f"{self._process}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            r = self._post(
                "/simulation/start",
                {
                    "execution_id": execution_id,
                    "historical_file": "_temp.json",
                    "real_time": False,
                },
            )
            if r.status_code not in (200, 201):
                detail = r.json().get("detail", r.text) if r.content else r.text
                self.simulation_failed.emit(f"Simulation start failed: {detail}")
                return
        except requests.RequestException as exc:
            self.simulation_failed.emit(f"Could not start simulation: {exc}")
            return

        # 5. Poll status
        consecutive_failures = 0
        while True:
            self.msleep(1000)
            try:
                r = self._get("/status")
                r.raise_for_status()
                data = r.json()
                consecutive_failures = 0
            except requests.RequestException:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    self.simulation_failed.emit("Lost contact with simulation server.")
                    return
                continue

            sim_status = data.get("sim_status", "")
            current_t = float(data.get("current_t", 0.0))
            self.time_updated.emit(current_t)

            if sim_status == "idle":
                break
            if sim_status == "no_project":
                self.simulation_failed.emit(
                    "Server lost the project during simulation."
                )
                return

        # 6. Get DB path
        try:
            r = self._get("/simulation/db")
            r.raise_for_status()
            db_path = r.json().get("db_path", "")
            if not db_path:
                self.simulation_failed.emit("Server returned no DB path.")
                return
        except requests.RequestException as exc:
            self.simulation_failed.emit(f"Could not retrieve simulation DB path: {exc}")
            return

        self.simulation_done.emit(db_path)


# ---------------------------------------------------------------------------
# ProfilePlot
# ---------------------------------------------------------------------------


class ProfilePlot(QWidget):
    """Thin QWidget wrapper around a matplotlib canvas for time-series charts."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
        from matplotlib.figure import Figure

        self._fig = Figure(figsize=(4, 2.5), layout="constrained")
        self._canvas = FigureCanvasQTAgg(self._fig)
        self._ax = self._fig.add_subplot(111)
        self._cursor_line = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._canvas)

        self._show_placeholder("Click a component to see data")

    def _apply_theme(self) -> None:
        dark = isDarkTheme()
        bg = "#1e1e1e" if dark else "#ffffff"
        fg = "#cccccc" if dark else "#333333"
        grid = "#333333" if dark else "#dddddd"
        self._fig.patch.set_facecolor(bg)
        self._ax.set_facecolor(bg)
        for spine in self._ax.spines.values():
            spine.set_edgecolor(fg)
        self._ax.tick_params(colors=fg)
        self._ax.xaxis.label.set_color(fg)
        self._ax.yaxis.label.set_color(fg)
        self._ax.title.set_color(fg)
        self._ax.grid(True, color=grid, linewidth=0.5)

    def _show_placeholder(self, message: str) -> None:
        self._ax.clear()
        self._apply_theme()
        self._ax.text(
            0.5,
            0.5,
            message,
            transform=self._ax.transAxes,
            ha="center",
            va="center",
            fontsize=10,
            color="#888888",
        )
        self._ax.set_xticks([])
        self._ax.set_yticks([])
        self._canvas.draw_idle()

    def update_plot(
        self,
        series: Series,
        x_label: str,
        y_label: str,
        title: str,
        component: str = "",
        color_by_compound: bool = False,
    ) -> None:
        self._ax.clear()
        self._cursor_line = None  # clear() destroys the previous cursor artist too
        self._apply_theme()
        if not series:
            msg = f"No data for '{component}'" if component else "No data available"
            self._ax.text(
                0.5,
                0.5,
                msg,
                transform=self._ax.transAxes,
                ha="center",
                va="center",
                fontsize=10,
                color="#888888",
            )
            self._ax.set_xticks([])
            self._ax.set_yticks([])
        else:
            for label, (xs, ys) in series.items():
                color, alpha = (
                    _compound_series_style(label) if color_by_compound else (None, 1.0)
                )
                self._ax.plot(
                    xs, ys, label=label, linewidth=1.2, color=color, alpha=alpha
                )
            self._ax.set_xlabel(x_label, fontsize=8)
            self._ax.set_ylabel(y_label, fontsize=8)
            self._ax.set_title(title, fontsize=9)
            if len(series) > 1:
                self._ax.legend(fontsize=7, loc="best")
        self._canvas.draw_idle()

    def set_cursor(self, t: float | None) -> None:
        """Show (or move) a vertical marker at time *t*, or hide it if None."""
        if t is None:
            if self._cursor_line is not None:
                self._cursor_line.set_visible(False)
                self._canvas.draw_idle()
            return
        if self._cursor_line is None:
            self._cursor_line = self._ax.axvline(
                t, color="#e04b4b", linewidth=1, linestyle="--", zorder=5
            )
        else:
            self._cursor_line.set_xdata([t, t])
            self._cursor_line.set_visible(True)
        self._canvas.draw_idle()


# ---------------------------------------------------------------------------
# ProfilesWidget
# ---------------------------------------------------------------------------

_LENGTH_PROFILE_KEY = "length_profile"

_SEGMENTS = [
    ("temperature", "Temperature"),
    ("pressure", "Pressure"),
    ("flow", "Flow"),
    ("content", "Content"),
    (_LENGTH_PROFILE_KEY, "Length Profile"),
]

_PLOT_META = {
    "temperature": ("Time (s)", "Temperature (°C)", "Temperature"),
    "pressure": ("Time (s)", "Pressure (bar)", "Pressure"),
    "flow": ("Time (s)", "Flow (mL/min)", "Flow"),
    "content": ("Time (s)", "Moles (mol)", "Content"),
    _LENGTH_PROFILE_KEY: ("Position (mm)", "Moles (mol)", "Length Profile"),
}


class ProfilesWidget(QWidget):
    """Panel that shows per-component simulation profiles below the graph."""

    scrub_requested = pyqtSignal(float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db_path: Path | None = None
        self._component: str = ""
        self._edge_id: str | None = None
        self._running_process: str = ""
        self._scrub_times: list[float] = []
        self._pending_scrub_index: int | None = None
        self._suppress_scrub_signal = False
        self._last_scrub_time: float | None = None

        # --- Header stack: normal label vs. running indicator ---
        self._header_stack = QStackedWidget(self)

        # page 0 — normal
        self._label = BodyLabel("Click a component to see its profiles", self)
        self._label.setWordWrap(True)
        self._header_stack.addWidget(self._label)

        # page 1 — simulation running
        _running_page = QWidget(self)
        _running_layout = QHBoxLayout(_running_page)
        _running_layout.setContentsMargins(0, 0, 0, 0)
        _running_layout.setSpacing(8)
        self._progress_ring = IndeterminateProgressRing(_running_page)
        self._progress_ring.setFixedSize(24, 24)
        self._running_label = BodyLabel("Simulating…", _running_page)
        _running_layout.addWidget(self._progress_ring)
        _running_layout.addWidget(self._running_label, 1)
        self._header_stack.addWidget(_running_page)

        # --- Scrub bar: time slider, shown once there are >=2 recorded frames ---
        self._scrub_bar = QWidget(self)
        _scrub_layout = QHBoxLayout(self._scrub_bar)
        _scrub_layout.setContentsMargins(0, 0, 0, 4)
        _scrub_layout.setSpacing(8)
        self._scrub_slider = Slider(Qt.Horizontal, self._scrub_bar)
        self._scrub_slider.setRange(0, 0)
        self._scrub_time_label = CaptionLabel("t = 0.0s / 0.0s", self._scrub_bar)
        _scrub_layout.addWidget(self._scrub_slider, 1)
        _scrub_layout.addWidget(self._scrub_time_label)
        self._scrub_bar.hide()

        self._scrub_slider.valueChanged.connect(self._on_scrub_value_changed)
        self._scrub_slider.sliderReleased.connect(self._flush_scrub)

        self._scrub_timer = QTimer(self)
        self._scrub_timer.setSingleShot(True)
        self._scrub_timer.setInterval(33)  # ~30 fps cap while dragging
        self._scrub_timer.timeout.connect(self._emit_scrub)

        # --- Segment control & plot stack ---
        self._segment = SegmentedWidget(self)
        self._plot_stack = QStackedWidget(self)

        self._plots: dict[str, ProfilePlot] = {}
        for key, text in _SEGMENTS:
            plot = ProfilePlot(self)
            self._plots[key] = plot
            self._plot_stack.addWidget(plot)
            self._segment.addItem(routeKey=key, text=text)
        self._time_series_keys = [
            key for key, _ in _SEGMENTS if key != _LENGTH_PROFILE_KEY
        ]

        self._segment.currentItemChanged.connect(self._switch)
        self._segment.setCurrentItem(_SEGMENTS[0][0])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(4)
        layout.addWidget(self._header_stack)
        layout.addWidget(self._scrub_bar)
        layout.addWidget(self._segment)
        layout.addWidget(self._plot_stack, 1)

    def _switch(self, key: str) -> None:
        plot = self._plots.get(key)
        if plot is not None:
            self._plot_stack.setCurrentWidget(plot)

    # --- Scrub bar ---

    def set_scrub_times(self, times: list[float]) -> None:
        """Configure the scrub slider for a newly opened simulation run.

        *times* is the full sorted list of recorded snapshot instants. Hidden
        when there are fewer than two recorded frames — nothing to scrub
        between.
        """
        self._scrub_times = list(times)
        self._scrub_timer.stop()
        self._pending_scrub_index = None

        if len(self._scrub_times) < 2:
            self._scrub_bar.hide()
            return

        last_index = len(self._scrub_times) - 1
        self._suppress_scrub_signal = True
        try:
            self._scrub_slider.setMinimum(0)
            self._scrub_slider.setMaximum(last_index)
            self._scrub_slider.setValue(last_index)
        finally:
            self._suppress_scrub_signal = False
        self._update_scrub_label(last_index)
        self._scrub_bar.show()

    def set_cursor_time(self, t: float | None) -> None:
        """Move the vertical cursor marker on the time-series plots to *t*,
        and re-query + redraw the Length Profile snapshot for the new time
        (it has no time axis to put a cursor on - it must be redrawn instead).
        """
        self._last_scrub_time = t
        for key in self._time_series_keys:
            self._plots[key].set_cursor(t)
        self._refresh_length_profile()

    def _update_scrub_label(self, index: int) -> None:
        t = self._scrub_times[index]
        total = self._scrub_times[-1]
        self._scrub_time_label.setText(f"t = {t:.1f}s / {total:.1f}s")

    def _on_scrub_value_changed(self, index: int) -> None:
        if self._suppress_scrub_signal:
            return
        if not (0 <= index < len(self._scrub_times)):
            return
        self._update_scrub_label(index)
        self._pending_scrub_index = index
        if not self._scrub_timer.isActive():
            self._scrub_timer.start()

    def _emit_scrub(self) -> None:
        if self._pending_scrub_index is None:
            return
        index, self._pending_scrub_index = self._pending_scrub_index, None
        self.scrub_requested.emit(self._scrub_times[index])

    def _flush_scrub(self) -> None:
        self._scrub_timer.stop()
        self._emit_scrub()

    # --- Simulation state ---

    def show_running(self, process_name: str) -> None:
        self._running_process = process_name
        self._running_label.setText(f"Simulating {process_name}…")
        self._header_stack.setCurrentIndex(1)
        self._progress_ring.start()
        self._scrub_bar.hide()
        for plot in self._plots.values():
            plot._show_placeholder("Simulation running…")

    def update_sim_time(self, current_t: float) -> None:
        if self._header_stack.currentIndex() == 1:
            self._running_label.setText(
                f"Simulating {self._running_process}… t = {current_t:.1f} s"
            )

    def show_sim_error(self, message: str) -> None:
        self._progress_ring.stop()
        self._header_stack.setCurrentIndex(0)
        self._label.setText(f"Simulation error: {message}")
        for plot in self._plots.values():
            plot._show_placeholder("Simulation failed")
        if len(self._scrub_times) >= 2:
            # A previous successful run's scrub session is still valid — restore it
            # rather than stranding the user with no scrubbable data.
            self._scrub_bar.show()

    def on_sim_done(self) -> None:
        self._progress_ring.stop()
        self._header_stack.setCurrentIndex(0)
        self._label.setText("Click a component to see its profiles")

    # --- Normal profile loading ---

    def set_db(self, db_path: Path | None) -> None:
        self._db_path = db_path

    def load_component(self, name: str) -> None:
        self._component = name
        if not name:
            self._label.setText("Click a component to see its profiles")
            for key in self._time_series_keys:
                self._plots[key]._show_placeholder("Click a component to see data")
            return

        self._label.setText(name)

        if self._db_path is None or not self._db_path.exists():
            for key in self._time_series_keys:
                self._plots[key]._show_placeholder("No simulation data loaded")
            return

        try:
            reader = SimDbReader(self._db_path)
        except Exception as exc:
            logger.warning(f"Could not open simulation DB: {exc}")
            for key in self._time_series_keys:
                self._plots[key]._show_placeholder("Could not open simulation database")
            return

        try:
            data = {
                "temperature": reader.temperature(name),
                "pressure": reader.pressure(name),
                "flow": reader.flow(name),
                "content": reader.content(name),
            }
        finally:
            reader.close()

        for key in self._time_series_keys:
            plot = self._plots[key]
            x_label, y_label, title = _PLOT_META[key]
            plot.update_plot(
                data[key],
                x_label,
                y_label,
                title,
                component=name,
                color_by_compound=(key == "content"),
            )
            plot.set_cursor(self._last_scrub_time)

    def load_edge_profile(self, edge_id: str | None) -> None:
        """Select which edge feeds the Length Profile tab.

        Independent of `_component`/`load_component()`: `_component` is a
        fuzzy, prefix-matched label spanning 4 different tables, while
        `edge_id` is an exact primary-key match against
        edge_cells/cell_state/cell_content. Pass None when the current
        selection has no associated tube (vessel, pump, valve, ...).
        """
        self._edge_id = edge_id
        self._refresh_length_profile()

    def _refresh_length_profile(self) -> None:
        plot = self._plots[_LENGTH_PROFILE_KEY]
        if self._edge_id is None:
            plot._show_placeholder("Not applicable for this selection")
            return
        if self._db_path is None or not self._db_path.exists():
            plot._show_placeholder("No simulation data loaded")
            return
        if self._last_scrub_time is None:
            plot._show_placeholder("No time selected")
            return

        try:
            reader = SimDbReader(self._db_path)
        except Exception as exc:
            logger.warning(f"Could not open simulation DB: {exc}")
            plot._show_placeholder("Could not open simulation database")
            return

        try:
            series = reader.length_profile(self._edge_id, self._last_scrub_time)
        finally:
            reader.close()

        x_label, y_label, title = _PLOT_META[_LENGTH_PROFILE_KEY]
        plot.update_plot(
            series,
            x_label,
            y_label,
            title,
            component=self._edge_id,
            color_by_compound=True,
        )


# ---------------------------------------------------------------------------
# SimulateWindowReport
# ---------------------------------------------------------------------------


class SimulateWindowReport(QMainWindow):

    def __init__(self, graph: SimGraphicView, parent: "SetupWindow") -> None:
        super().__init__(parent)
        self._setup_window = parent
        self._process: str = ""
        self._worker: SimRunWorker | None = None
        self._playback: SimulationPlayback | None = None

        self.widget_profiles = ProfilesWidget()
        self.central = FrameBase(
            parent=parent,
            graph=graph,
            workflow=self.widget_profiles,
        )
        self.setCentralWidget(self.central)
        self.initNavigation()

        scene = graph.scene_attribute
        scene.selectionChanged.connect(self._on_selection_changed)
        self.widget_profiles.scrub_requested.connect(self._on_scrub_requested)

    def initNavigation(self) -> None:
        self.central.addNavigationAction(
            icon=OrchestratorIcon.HOME,
            text="Home",
            onClick=self.recenter_views,
            position=NavigationItemPosition.TOP,
            tooltip="Recenter the view",
        )
        self.central.workflowFrame.setMinimumHeight(100)

    def simulate(self, process: str, project_path: Path | str) -> None:
        """Start a workflow simulation for *process* against *project_path*."""
        if self._worker is not None and self._worker.isRunning():
            logger.warning("Simulation already running; ignoring new request.")
            return

        self._process = process
        project_path = Path(project_path)

        self.widget_profiles.show_running(process)

        self._worker = SimRunWorker(process, project_path, parent=self)
        self._worker.status_changed.connect(self.widget_profiles.show_running)
        self._worker.time_updated.connect(self.widget_profiles.update_sim_time)
        self._worker.simulation_done.connect(self._on_sim_done)
        self._worker.simulation_failed.connect(self._on_sim_failed)
        self._worker.start()

    def recenter_views(self) -> None:
        self.central._graph.recenter_view()  # type: ignore

    def _on_sim_done(self, db_path: str) -> None:
        self.widget_profiles.on_sim_done()
        self.widget_profiles.set_db(Path(db_path))
        if self.widget_profiles._component:
            self.widget_profiles.load_component(self.widget_profiles._component)

        self._close_playback()
        self._playback = SimulationPlayback.open(Path(db_path))
        times = self._playback.times if self._playback is not None else []
        self.widget_profiles.set_scrub_times(times)
        if times:
            self._apply_scrub(times[-1])

    def _on_sim_failed(self, message: str) -> None:
        logger.error(f"Simulation failed: {message}")
        self.widget_profiles.show_sim_error(message)

    def _close_playback(self) -> None:
        if self._playback is not None:
            self._playback.close()
            self._playback = None

    def _on_scrub_requested(self, t: float) -> None:
        self._apply_scrub(t)

    def _apply_scrub(self, t: float) -> None:
        if self._playback is None:
            return
        self._playback.apply_at_time(
            t,
            self._setup_window.orchestrator.components,
            self._setup_window.orchestrator.connections,
        )
        self.widget_profiles.set_cursor_time(t)

    def closeEvent(self, a0) -> None:
        self._close_playback()
        super().closeEvent(a0)

    def _on_selection_changed(self) -> None:
        from chemunited_core.components.plugflow import PlugFlowComponentData

        from chemunited.elements.component.graph_item import GraphComponent
        from chemunited.elements.connection.connection import HydraulicConnectionItem

        scene = self.central._graph.scene_attribute  # type: ignore
        if sip.isdeleted(scene):
            return
        for item in scene.selectedItems():
            if isinstance(item, GraphComponent):
                self.widget_profiles.load_component(item.inf.name)
                edge_id = None
                if isinstance(item.inf, PlugFlowComponentData):
                    origin, destination = next(iter(item.inf.internal_edges))
                    edge_id = f"{item.inf.name}.{origin}.{destination}"
                self.widget_profiles.load_edge_profile(edge_id)
                return
            if isinstance(item, HydraulicConnectionItem):
                self.widget_profiles.load_component(item.inf.name)
                self.widget_profiles.load_edge_profile(item.inf.name)
                return
        self.widget_profiles.load_component("")
        self.widget_profiles.load_edge_profile(None)
