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
from loguru import logger
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    IndeterminateProgressRing,
    NavigationItemPosition,
    SegmentedWidget,
    isDarkTheme,
)

from chemunited.shared.icon import OrchestratorIcon
from chemunited.shared.widgets.frame_base import FrameBase

from .graph_simulation import SimGraphicView

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

        self._fig = Figure(figsize=(4, 2.5), tight_layout=True)
        self._canvas = FigureCanvasQTAgg(self._fig)
        self._ax = self._fig.add_subplot(111)

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
    ) -> None:
        self._ax.clear()
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
                self._ax.plot(xs, ys, label=label, linewidth=1.2)
            self._ax.set_xlabel(x_label, fontsize=8)
            self._ax.set_ylabel(y_label, fontsize=8)
            self._ax.set_title(title, fontsize=9)
            if len(series) > 1:
                self._ax.legend(fontsize=7, loc="best")
        self._canvas.draw_idle()


# ---------------------------------------------------------------------------
# ProfilesWidget
# ---------------------------------------------------------------------------

_SEGMENTS = [
    ("temperature", "Temperature"),
    ("pressure", "Pressure"),
    ("flow", "Flow"),
    ("content", "Content"),
]

_PLOT_META = {
    "temperature": ("Time (s)", "Temperature (°C)", "Temperature"),
    "pressure": ("Time (s)", "Pressure (bar)", "Pressure"),
    "flow": ("Time (s)", "Flow (mL/min)", "Flow"),
    "content": ("Time (s)", "Moles (mol)", "Content"),
}


class ProfilesWidget(QWidget):
    """Panel that shows per-component simulation profiles below the graph."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._db_path: Path | None = None
        self._component: str = ""
        self._running_process: str = ""

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

        # --- Segment control & plot stack ---
        self._segment = SegmentedWidget(self)
        self._plot_stack = QStackedWidget(self)

        self._plots: dict[str, ProfilePlot] = {}
        for key, text in _SEGMENTS:
            plot = ProfilePlot(self)
            self._plots[key] = plot
            self._plot_stack.addWidget(plot)
            self._segment.addItem(
                routeKey=key, text=text, onClick=lambda k=key: self._switch(k)
            )

        self._segment.setCurrentItem(_SEGMENTS[0][0])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 4)
        layout.setSpacing(4)
        layout.addWidget(self._header_stack)
        layout.addWidget(self._segment)
        layout.addWidget(self._plot_stack, 1)

    def _switch(self, key: str) -> None:
        plot = self._plots.get(key)
        if plot is not None:
            self._plot_stack.setCurrentWidget(plot)

    # --- Simulation state ---

    def show_running(self, process_name: str) -> None:
        self._running_process = process_name
        self._running_label.setText(f"Simulating {process_name}…")
        self._header_stack.setCurrentIndex(1)
        self._progress_ring.start()
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
            for plot in self._plots.values():
                plot._show_placeholder("Click a component to see data")
            return

        self._label.setText(name)

        if self._db_path is None or not self._db_path.exists():
            for plot in self._plots.values():
                plot._show_placeholder("No simulation data loaded")
            return

        try:
            reader = SimDbReader(self._db_path)
        except Exception as exc:
            logger.warning(f"Could not open simulation DB: {exc}")
            for plot in self._plots.values():
                plot._show_placeholder("Could not open simulation database")
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

        for key, plot in self._plots.items():
            x_label, y_label, title = _PLOT_META[key]
            plot.update_plot(data[key], x_label, y_label, title, component=name)


# ---------------------------------------------------------------------------
# SimulateWindowReport
# ---------------------------------------------------------------------------


class SimulateWindowReport(QMainWindow):

    def __init__(self, graph: SimGraphicView, parent: "SetupWindow") -> None:
        super().__init__(parent)
        self._process: str = ""
        self._worker: SimRunWorker | None = None

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

    def initNavigation(self) -> None:
        self.central.addNavigationAction(
            icon=OrchestratorIcon.HOME,
            text="Home",
            onClick=self.recenter_views,
            position=NavigationItemPosition.TOP,
            tooltip="Recenter the view",
        )

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

    def _on_sim_failed(self, message: str) -> None:
        logger.error(f"Simulation failed: {message}")
        self.widget_profiles.show_sim_error(message)

    def _on_selection_changed(self) -> None:
        from chemunited.elements.component.graph_item import GraphComponent

        scene = self.central._graph.scene_attribute  # type: ignore
        for item in scene.selectedItems():
            if isinstance(item, GraphComponent):
                self.widget_profiles.load_component(item.inf.name)
                return
        self.widget_profiles.load_component("")
