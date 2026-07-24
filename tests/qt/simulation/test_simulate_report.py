from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from chemunited_core.compounds import COMPOUNDS, ChemicalEntity
from chemunited_sim.recorder.schema import create_all_tables
from matplotlib.colors import to_hex
from pytestqt.qtbot import QtBot

from chemunited.elements.component.glossary.valve.solenoid_valve_graph import (
    StatusOverlaySolenoid,
)
from chemunited.setup import SetupWindow
from chemunited.simulation.simulate_report import (
    _LENGTH_PROFILE_KEY,
    ProfilePlot,
    ProfilesWidget,
    SimDbReader,
)

_THROTTLE_WAIT_MS = 80  # comfortably above the 33ms scrub-timer interval


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    create_all_tables(conn)
    return conn


class TestProfilesWidgetScrubBar:
    def test_set_scrub_times_hides_bar_for_fewer_than_two_frames(
        self, qtbot: QtBot
    ) -> None:
        widget = ProfilesWidget()
        qtbot.addWidget(widget)

        widget.set_scrub_times([])
        assert widget._scrub_bar.isHidden()

        widget.set_scrub_times([1.0])
        assert widget._scrub_bar.isHidden()

    def test_set_scrub_times_configures_slider_bounds_and_label(
        self, qtbot: QtBot
    ) -> None:
        widget = ProfilesWidget()
        qtbot.addWidget(widget)

        widget.set_scrub_times([0.0, 24.0, 48.0])

        assert widget._scrub_slider.minimum() == 0
        assert widget._scrub_slider.maximum() == 2
        assert widget._scrub_slider.value() == 2
        assert widget._scrub_time_label.text() == "t = 48.0s / 48.0s"
        assert not widget._scrub_bar.isHidden()

    def test_setting_slider_value_emits_scrub_requested_after_throttle(
        self, qtbot: QtBot
    ) -> None:
        widget = ProfilesWidget()
        qtbot.addWidget(widget)
        widget.set_scrub_times([0.0, 24.0, 48.0])

        with qtbot.waitSignal(widget.scrub_requested, timeout=500) as blocker:
            widget._scrub_slider.setValue(1)

        assert blocker.args == [24.0]

    def test_rapid_slider_moves_are_throttled_to_one_emission(
        self, qtbot: QtBot
    ) -> None:
        widget = ProfilesWidget()
        qtbot.addWidget(widget)
        widget.set_scrub_times([0.0, 24.0, 48.0])

        received: list[float] = []
        widget.scrub_requested.connect(received.append)

        widget._scrub_slider.setValue(0)
        widget._scrub_slider.setValue(1)
        qtbot.wait(_THROTTLE_WAIT_MS)

        assert received == [24.0]


class TestSimDbReaderLengthProfile:
    def test_length_profile_builds_staircase_with_zero_fill(
        self, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "sim.db"
        conn = _connect(db_path)
        conn.executemany(
            "INSERT INTO edge_cells (edge_id, cell_index, position_m, length_m) "
            "VALUES (?, ?, ?, ?)",
            [
                ("e1", 0, 0.0, 0.01),  # origin end, 10mm
                ("e1", 1, 0.01, 0.02),  # destination end, 20mm
            ],
        )
        conn.executemany(
            "INSERT INTO cell_state "
            "(time, edge_id, cell_index, phase, phase_fraction, temperature) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1.0, "e1", 0, "liquid", 1.0, 298.15),
                (1.0, "e1", 1, "liquid", 1.0, 298.15),
            ],
        )
        conn.executemany(
            "INSERT INTO cell_content "
            "(time, edge_id, cell_index, phase, species_id, moles) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1.0, "e1", 0, "liquid", "red_dye", 0.001),
                (1.0, "e1", 1, "liquid", "blue_dye", 0.002),
            ],
        )
        conn.commit()
        conn.close()

        reader = SimDbReader(db_path)
        try:
            series = reader.length_profile("e1", 1.0)
        finally:
            reader.close()

        assert set(series) == {"liquid / red_dye", "liquid / blue_dye"}
        # red_dye only lives in cell 0 (0-10mm) - must 0-fill across cell 1 (10-30mm)
        assert series["liquid / red_dye"] == (
            [0.0, 10.0, 10.0, 30.0],
            [0.001, 0.001, 0.0, 0.0],
        )
        # blue_dye only lives in cell 1 - must 0-fill across cell 0
        assert series["liquid / blue_dye"] == (
            [0.0, 10.0, 10.0, 30.0],
            [0.0, 0.0, 0.002, 0.002],
        )

    def test_length_profile_returns_empty_for_unknown_or_empty_edge(
        self, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "sim.db"
        _connect(db_path).close()

        reader = SimDbReader(db_path)
        try:
            assert reader.length_profile("missing", 1.0) == {}
        finally:
            reader.close()


class TestProfilesWidgetLengthProfile:
    def test_load_edge_profile_none_shows_placeholder(self, qtbot: QtBot) -> None:
        widget = ProfilesWidget()
        qtbot.addWidget(widget)

        widget.load_edge_profile(None)

        plot = widget._plots[_LENGTH_PROFILE_KEY]
        assert len(plot._ax.lines) == 0

    def test_load_edge_profile_plots_series_for_selected_edge(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        db_path = tmp_path / "sim.db"
        conn = _connect(db_path)
        conn.executemany(
            "INSERT INTO edge_cells (edge_id, cell_index, position_m, length_m) "
            "VALUES (?, ?, ?, ?)",
            [("e1", 0, 0.0, 0.01)],
        )
        conn.executemany(
            "INSERT INTO cell_state "
            "(time, edge_id, cell_index, phase, phase_fraction, temperature) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(1.0, "e1", 0, "liquid", 1.0, 298.15)],
        )
        conn.execute(
            "INSERT INTO cell_content "
            "(time, edge_id, cell_index, phase, species_id, moles) VALUES (?, ?, ?, ?, ?, ?)",
            (1.0, "e1", 0, "liquid", "red_dye", 0.001),
        )
        conn.commit()
        conn.close()

        widget = ProfilesWidget()
        qtbot.addWidget(widget)
        widget.set_db(db_path)
        widget.set_cursor_time(1.0)

        widget.load_edge_profile("e1")

        plot = widget._plots[_LENGTH_PROFILE_KEY]
        assert len(plot._ax.lines) == 1
        assert list(plot._ax.lines[0].get_ydata()) == [0.001, 0.001]


class TestSimulateWindowReportPlayback:
    def _build_window(self, qtbot: QtBot) -> SetupWindow:
        window = SetupWindow()
        qtbot.addWidget(window)
        window.show()
        qtbot.waitExposed(window)
        return window

    def _add_platform(self, window: SetupWindow) -> None:
        window.orchestrator.add_component(
            name="BottleA",
            figure="GlassBottle",
            position=(0.0, 0.0),
            capacity="10 ml",
        )
        window.orchestrator.add_component(
            name="PumpA",
            figure="HPLCPump",
            position=(200.0, 0.0),
        )
        window.orchestrator.add_component(
            name="PumpB",
            figure="HPLCPump",
            position=(400.0, 0.0),
        )
        window.orchestrator.add_connection(
            origin="PumpA",
            destiny="PumpB",
            origin_port=2,
            destiny_port=1,
        )
        window.orchestrator.add_component(
            name="Sol1",
            figure="SolenoidValve",
            position=(600.0, 0.0),
        )

    def _build_two_frame_db(self, db_path: Path) -> None:
        conn = _connect(db_path)
        conn.executemany(
            "INSERT INTO node_pressure (time, node_id, pressure) VALUES (?, ?, ?)",
            [(0.0, "BottleA.1", 101325.0), (24.0, "BottleA.1", 101325.0)],
        )
        conn.executemany(
            "INSERT INTO inventory_content "
            "(time, node_id, phase, species_id, moles, volume) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (0.0, "BottleA.Inventory", "liquid", "red_dye", 0.01, 1e-6),
                (24.0, "BottleA.Inventory", "liquid", "red_dye", 0.05, 5e-6),
            ],
        )
        conn.executemany(
            "INSERT INTO edge_cells (edge_id, cell_index, position_m, length_m) "
            "VALUES (?, ?, ?, ?)",
            [("PumpA_2_PumpB_1", 0, 0.0, 0.01)],
        )
        conn.executemany(
            "INSERT INTO cell_state "
            "(time, edge_id, cell_index, phase, phase_fraction, temperature) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (0.0, "PumpA_2_PumpB_1", 0, "liquid", 1.0, 298.15),
                (24.0, "PumpA_2_PumpB_1", 0, "liquid", 1.0, 298.15),
            ],
        )
        conn.executemany(
            "INSERT INTO cell_content "
            "(time, edge_id, cell_index, phase, species_id, moles) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (0.0, "PumpA_2_PumpB_1", 0, "liquid", "blue_dye", 0.002),
                (24.0, "PumpA_2_PumpB_1", 0, "liquid", "blue_dye", 0.009),
            ],
        )
        conn.executemany(
            "INSERT INTO component_state (time, component, state) VALUES (?, ?, ?)",
            [
                (0.0, "Sol1", '{"opened": true}'),
                (24.0, "Sol1", '{"opened": false}'),
            ],
        )
        conn.commit()
        conn.close()

    def test_on_sim_done_opens_playback_and_paints_last_frame(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        window = self._build_window(qtbot)
        self._add_platform(window)
        db_path = tmp_path / "sim.db"
        self._build_two_frame_db(db_path)

        window.SimulateWindowReport._on_sim_done(str(db_path))

        report = window.SimulateWindowReport
        assert report.widget_profiles._scrub_times == [0.0, 24.0]
        assert report.widget_profiles._scrub_slider.value() == 1

        bottle = window.orchestrator.components["BottleA"].inf.internal_inventory
        assert bottle.liq_content.initial_species == {"red_dye": 0.05}

        edge = window.orchestrator.connections["PumpA_2_PumpB_1"].inf
        assert len(edge.content) == 1
        assert edge.content[0].initial_species == {"blue_dye": 0.009}

        solenoid = window.orchestrator.components["Sol1"].inf
        assert solenoid.opened is False  # last frame (t=24)

    def test_scrubbing_updates_canvas_to_selected_frame(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        window = self._build_window(qtbot)
        self._add_platform(window)
        db_path = tmp_path / "sim.db"
        self._build_two_frame_db(db_path)
        window.SimulateWindowReport._on_sim_done(str(db_path))

        window.SimulateWindowReport.widget_profiles._scrub_slider.setValue(0)
        qtbot.wait(_THROTTLE_WAIT_MS)

        bottle = window.orchestrator.components["BottleA"].inf.internal_inventory
        assert bottle.liq_content.initial_species == {"red_dye": 0.01}

        edge = window.orchestrator.connections["PumpA_2_PumpB_1"].inf
        assert edge.content[0].initial_species == {"blue_dye": 0.002}

        solenoid = window.orchestrator.components["Sol1"].inf
        assert solenoid.opened is True  # first frame (t=0)

    def test_scrubbing_updates_solenoid_valve_overlay(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        window = self._build_window(qtbot)
        self._add_platform(window)
        db_path = tmp_path / "sim.db"
        self._build_two_frame_db(db_path)
        window.SimulateWindowReport._on_sim_done(str(db_path))

        overlay = window.orchestrator.components["Sol1"].graph._overlay
        assert overlay.isVisible()
        assert (
            overlay._color == StatusOverlaySolenoid.COLOR_CLOSED
        )  # closed at t=24 (last frame)

        window.SimulateWindowReport.widget_profiles._scrub_slider.setValue(0)
        qtbot.wait(_THROTTLE_WAIT_MS)

        assert overlay._color == StatusOverlaySolenoid.COLOR_ACTIVE  # open at t=0

    def test_on_sim_done_closes_previous_playback_before_opening_new(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        window = self._build_window(qtbot)
        self._add_platform(window)
        first_db = tmp_path / "sim1.db"
        second_db = tmp_path / "sim2.db"
        self._build_two_frame_db(first_db)
        self._build_two_frame_db(second_db)

        window.SimulateWindowReport._on_sim_done(str(first_db))
        first_playback = window.SimulateWindowReport._playback
        assert first_playback is not None

        window.SimulateWindowReport._on_sim_done(str(second_db))

        assert window.SimulateWindowReport._playback is not first_playback
        try:
            first_playback._conn.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            pass
        else:
            raise AssertionError(
                "expected the previous playback connection to be closed"
            )

    def test_selecting_connection_populates_and_rescrubs_length_profile(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        window = self._build_window(qtbot)
        self._add_platform(window)
        db_path = tmp_path / "sim.db"
        self._build_two_frame_db(db_path)
        window.SimulateWindowReport._on_sim_done(str(db_path))

        report = window.SimulateWindowReport
        connection = window.orchestrator.connections["PumpA_2_PumpB_1"]
        connection.setSelected(True)

        assert report.widget_profiles._edge_id == "PumpA_2_PumpB_1"
        plot = report.widget_profiles._plots[_LENGTH_PROFILE_KEY]
        assert list(plot._ax.lines[0].get_ydata()) == [0.009, 0.009]  # last frame, t=24

        report.widget_profiles._scrub_slider.setValue(0)
        qtbot.wait(_THROTTLE_WAIT_MS)

        assert list(plot._ax.lines[0].get_ydata()) == [0.002, 0.002]  # t=0

    def test_selecting_non_plugflow_component_clears_length_profile(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        window = self._build_window(qtbot)
        self._add_platform(window)
        db_path = tmp_path / "sim.db"
        self._build_two_frame_db(db_path)
        window.SimulateWindowReport._on_sim_done(str(db_path))

        report = window.SimulateWindowReport
        window.orchestrator.components["BottleA"].graph.setSelected(True)

        assert report.widget_profiles._edge_id is None
        plot = report.widget_profiles._plots[_LENGTH_PROFILE_KEY]
        assert len(plot._ax.lines) == 0

    def test_selecting_plugflow_component_derives_internal_edge_id(
        self, qtbot: QtBot, tmp_path: Path
    ) -> None:
        window = self._build_window(qtbot)
        window.orchestrator.add_component(
            name="FlowReactor1",
            figure="FlowReactor",
            position=(0.0, 0.0),
            length="10 mm",
            diameter="1 mm",
        )
        db_path = tmp_path / "sim.db"
        conn = _connect(db_path)
        conn.execute(
            "INSERT INTO node_pressure (time, node_id, pressure) VALUES (?, ?, ?)",
            (0.0, "FlowReactor1.1", 101325.0),
        )
        conn.executemany(
            "INSERT INTO edge_cells (edge_id, cell_index, position_m, length_m) "
            "VALUES (?, ?, ?, ?)",
            [("FlowReactor1.1.2", 0, 0.0, 0.01)],
        )
        conn.executemany(
            "INSERT INTO cell_state "
            "(time, edge_id, cell_index, phase, phase_fraction, temperature) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(0.0, "FlowReactor1.1.2", 0, "liquid", 1.0, 298.15)],
        )
        conn.execute(
            "INSERT INTO cell_content "
            "(time, edge_id, cell_index, phase, species_id, moles) VALUES (?, ?, ?, ?, ?, ?)",
            (0.0, "FlowReactor1.1.2", 0, "liquid", "red_dye", 0.004),
        )
        conn.commit()
        conn.close()

        window.SimulateWindowReport._on_sim_done(str(db_path))

        report = window.SimulateWindowReport
        window.orchestrator.components["FlowReactor1"].graph.setSelected(True)

        assert report.widget_profiles._edge_id == "FlowReactor1.1.2"
        plot = report.widget_profiles._plots[_LENGTH_PROFILE_KEY]
        assert list(plot._ax.lines[0].get_ydata()) == [0.004, 0.004]


class TestProfilePlotCompoundColors:
    @pytest.fixture(autouse=True)
    def reset_compounds(self):
        COMPOUNDS.clear()
        yield
        COMPOUNDS.clear()

    def test_content_series_uses_registered_compound_color(self, qtbot: QtBot) -> None:
        COMPOUNDS.register(
            ChemicalEntity(name="red_dye", color_red=200, color_green=10, color_blue=10)
        )
        plot = ProfilePlot()
        qtbot.addWidget(plot)

        plot.update_plot(
            {"BottleA.Inventory / liquid / red_dye": ([0.0, 1.0], [0.01, 0.02])},
            "Time (s)",
            "Moles (mol)",
            "Content",
            color_by_compound=True,
        )

        line = plot._ax.lines[0]
        assert to_hex(line.get_color()).upper() == "#C80A0A"
        assert line.get_alpha() == 1.0

    def test_gas_phase_series_uses_reduced_opacity(self, qtbot: QtBot) -> None:
        COMPOUNDS.register(
            ChemicalEntity(name="n2", color_red=0, color_green=100, color_blue=200)
        )
        plot = ProfilePlot()
        qtbot.addWidget(plot)

        plot.update_plot(
            {"gas / n2": ([0.0, 10.0], [0.0, 0.0])},
            "Position (mm)",
            "Moles (mol)",
            "Length Profile",
            color_by_compound=True,
        )

        line = plot._ax.lines[0]
        assert to_hex(line.get_color()).upper() == "#0064C8"
        assert line.get_alpha() == 0.5

    def test_unregistered_species_falls_back_to_default_cycle(
        self, qtbot: QtBot
    ) -> None:
        plot = ProfilePlot()
        qtbot.addWidget(plot)

        plot.update_plot(
            {"node / liquid / unknown_species": ([0.0, 1.0], [0.0, 1.0])},
            "Time (s)",
            "Moles (mol)",
            "Content",
            color_by_compound=True,
        )

        line = plot._ax.lines[0]
        assert line.get_alpha() == 1.0  # unregistered species still opaque, not crashed

    def test_non_content_tabs_ignore_compound_colors(self, qtbot: QtBot) -> None:
        COMPOUNDS.register(
            ChemicalEntity(name="red_dye", color_red=200, color_green=10, color_blue=10)
        )
        plot = ProfilePlot()
        qtbot.addWidget(plot)

        plot.update_plot(
            {"BottleA / liquid / red_dye": ([0.0, 1.0], [298.0, 300.0])},
            "Time (s)",
            "Temperature (°C)",
            "Temperature",
            color_by_compound=False,
        )

        line = plot._ax.lines[0]
        assert to_hex(line.get_color()).upper() != "#C80A0A"
