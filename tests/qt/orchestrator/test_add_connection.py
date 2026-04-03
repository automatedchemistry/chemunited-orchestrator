"""Tests for OrchestratorDraw.add_connection.

What is tested:
- add_connection registers the connection in orchestrator.connections
- add_connection places the connection's graph item in the scene
- Non-existent origin or destiny raises ValueError
- Non-existent port number on either side raises ValueError
- Adding a duplicate connection raises ValueError
"""
import pytest
from pytestqt.qtbot import QtBot

from chemunited.qt.setup import SetupWindow


class TestAddConnection:

    @pytest.fixture
    def window(self, qtbot: QtBot):
        w = SetupWindow()
        qtbot.addWidget(w)
        w.show()
        qtbot.waitExposed(w)
        return w

    @pytest.fixture
    def two_pumps(self, window: SetupWindow):
        """Window with two HPLCPump components already on the canvas."""
        window.orchestrator.add_component(
            name="PumpA", figure="HPLCPump", position=(0.0, 0.0)
        )
        window.orchestrator.add_component(
            name="PumpB", figure="HPLCPump", position=(200.0, 0.0)
        )
        return window

    # ── happy path ─────────────────────────────────────────────────────────

    def test_connection_registered_in_orchestrator(
        self, two_pumps: SetupWindow, screenshot
    ):
        screenshot(two_pumps, "initial")

        two_pumps.orchestrator.add_connection(
            origin="PumpA",
            destiny="PumpB",
            origin_port=2,
            destiny_port=1,
        )

        screenshot(two_pumps, "after_connection")

        assert "PumpA_2_PumpB_1" in two_pumps.orchestrator.connections

    def test_connection_graph_item_in_scene(
        self, two_pumps: SetupWindow, screenshot
    ):
        two_pumps.orchestrator.add_connection(
            origin="PumpA",
            destiny="PumpB",
            origin_port=2,
            destiny_port=1,
        )

        screenshot(two_pumps, "connection_in_scene")

        connection = two_pumps.orchestrator.connections["PumpA_2_PumpB_1"]
        assert connection in two_pumps.scene_attribute.items()

    # ── validation errors ──────────────────────────────────────────────────

    def test_nonexistent_origin_raises(self, two_pumps: SetupWindow):
        with pytest.raises(ValueError, match="does not exist"):
            two_pumps.orchestrator.add_connection(
                origin="Ghost",
                destiny="PumpB",
            )

    def test_nonexistent_destiny_raises(self, two_pumps: SetupWindow):
        with pytest.raises(ValueError, match="does not exist"):
            two_pumps.orchestrator.add_connection(
                origin="PumpA",
                destiny="Ghost",
            )

    def test_invalid_origin_port_raises(self, two_pumps: SetupWindow):
        with pytest.raises(ValueError, match="does not exist"):
            two_pumps.orchestrator.add_connection(
                origin="PumpA",
                destiny="PumpB",
                origin_port=99,
                destiny_port=1,
            )

    def test_invalid_destiny_port_raises(self, two_pumps: SetupWindow):
        with pytest.raises(ValueError, match="does not exist"):
            two_pumps.orchestrator.add_connection(
                origin="PumpA",
                destiny="PumpB",
                origin_port=2,
                destiny_port=99,
            )

    def test_duplicate_connection_raises(self, two_pumps: SetupWindow):
        two_pumps.orchestrator.add_connection(
            origin="PumpA",
            destiny="PumpB",
            origin_port=2,
            destiny_port=1,
        )

        with pytest.raises(ValueError, match="already exists"):
            two_pumps.orchestrator.add_connection(
                origin="PumpA",
                destiny="PumpB",
                origin_port=2,
                destiny_port=1,
            )
