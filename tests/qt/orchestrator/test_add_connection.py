"""Tests for OrchestratorDraw.add_connection / remove_connection.

What is tested:
- add_connection registers the connection in orchestrator.connections
- add_connection places the connection's graph item in the scene
- remove_connection unregisters the connection from orchestrator.connections
- remove_connection removes the graph item from the scene
- Removing a non-existent connection raises ValueError
- Non-existent origin or destiny raises ValueError
- Non-existent port number on either side raises ValueError
- Adding a duplicate connection raises ValueError
"""

import pytest
from chemunited_core.common.enums import ConnectionType
from pytestqt.qtbot import QtBot

from chemunited.setup import SetupWindow

CONNECTION_NAME = "PumpA_2_PumpB_1"


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

    @pytest.fixture
    def two_pumps_connected(self, two_pumps: SetupWindow):
        """Window with two HPLCPumps connected on port 2→1."""
        two_pumps.orchestrator.add_connection(
            origin="PumpA",
            destiny="PumpB",
            origin_port=2,
            destiny_port=1,
        )
        return two_pumps

    # ── add: happy path ────────────────────────────────────────────────────

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

        assert CONNECTION_NAME in two_pumps.orchestrator.connections

    def test_connection_graph_item_in_scene(self, two_pumps: SetupWindow, screenshot):
        two_pumps.orchestrator.add_connection(
            origin="PumpA",
            destiny="PumpB",
            origin_port=2,
            destiny_port=1,
        )

        screenshot(two_pumps, "connection_in_scene")

        connection = two_pumps.orchestrator.connections[CONNECTION_NAME]
        assert connection in two_pumps.scene_attribute.items()

    def test_draw_graph_layer_order_toggle_applies_to_existing_and_new_items(
        self, two_pumps_connected: SetupWindow
    ):
        window = two_pumps_connected
        graph = window.drawGraph
        components = [
            window.orchestrator.components["PumpA"].graph,
            window.orchestrator.components["PumpB"].graph,
        ]
        connection = window.orchestrator.connections[CONNECTION_NAME]

        assert graph._component_to_front is False
        assert all(connection.zValue() > component.zValue() for component in components)

        graph._bring_component_to_front_context_menu_event(True)

        assert graph._component_to_front is True
        assert graph._add_context_menu_event["bring_component_to_front"][
            "checked"
        ] is True
        assert all(component.zValue() > connection.zValue() for component in components)

        connection.addInflectionPoint()
        graph.apply_layer_order()

        handle = connection._handles[0]
        assert handle.parentItem() is connection
        assert handle.zValue() > 0

        window.orchestrator.add_component(
            name="PumpC", figure="HPLCPump", position=(400.0, 0.0)
        )
        window.orchestrator.add_connection(
            origin="PumpB",
            destiny="PumpC",
            origin_port=2,
            destiny_port=1,
        )

        new_component = window.orchestrator.components["PumpC"].graph
        new_connection = window.orchestrator.connections["PumpB_2_PumpC_1"]
        assert all(
            component.zValue() > new_connection.zValue()
            for component in [*components, new_component]
        )

        graph._bring_component_to_front_context_menu_event(False)

        assert graph._component_to_front is False
        assert graph._add_context_menu_event["bring_component_to_front"][
            "checked"
        ] is False
        assert connection.zValue() > new_component.zValue()
        assert new_connection.zValue() > components[0].zValue()

    def test_moved_inflection_point_is_saved_in_draw_data(
        self, two_pumps_connected: SetupWindow
    ):
        connection = two_pumps_connected.orchestrator.connections[CONNECTION_NAME]
        connection.addInflectionPoint()
        connection._handles[0].setPos(123.0, 45.0)

        assert connection.inf.inflection_points == [(123.0, 45.0)]

        draw_data = two_pumps_connected.orchestrator._build_draw_data()

        assert draw_data["connections"][0]["inflection_points"] == [[123.0, 45.0]]

    def test_saved_movement_connection_can_use_mixed_port_categories(
        self, window: SetupWindow
    ):
        window.orchestrator.add_component(
            name="Tray-A1",
            figure="Vial",
            position=(0.0, 0.0),
        )
        window.orchestrator.add_component(
            name="gantry",
            figure="Gantry3D",
            position=(100.0, 0.0),
            connections_number=1,
        )

        window.orchestrator.add_connection(
            origin="Tray-A1",
            destiny="gantry",
            origin_port=1,
            destiny_port=2,
            classification="movement",
        )

        connection = window.orchestrator.connections["Tray-A1_1_gantry_2"]
        assert connection.inf.classification == ConnectionType.MOVEMENT

    # ── remove: happy path ─────────────────────────────────────────────────

    def test_remove_connection_unregisters_from_orchestrator(
        self, two_pumps_connected: SetupWindow, screenshot
    ):
        screenshot(two_pumps_connected, "before_remove")

        two_pumps_connected.orchestrator.remove_connection(CONNECTION_NAME)

        screenshot(two_pumps_connected, "after_remove")

        assert CONNECTION_NAME not in two_pumps_connected.orchestrator.connections

    def test_remove_connection_removes_graph_item_from_scene(
        self, two_pumps_connected: SetupWindow, screenshot
    ):
        connection = two_pumps_connected.orchestrator.connections[CONNECTION_NAME]

        two_pumps_connected.orchestrator.remove_connection(CONNECTION_NAME)

        screenshot(two_pumps_connected, "after_remove")

        assert connection not in two_pumps_connected.scene_attribute.items()

    def test_remove_component_cascades_connection_removal(
        self, two_pumps_connected: SetupWindow
    ):
        """Removing a component must also remove any connections attached to it."""
        connection = two_pumps_connected.orchestrator.connections[CONNECTION_NAME]

        two_pumps_connected.orchestrator.remove_component("PumpA")

        assert CONNECTION_NAME not in two_pumps_connected.orchestrator.connections
        assert connection not in two_pumps_connected.scene_attribute.items()

    # ── remove: validation errors ──────────────────────────────────────────

    def test_remove_nonexistent_connection_raises(self, two_pumps: SetupWindow):
        with pytest.raises(ValueError, match="does not exist"):
            two_pumps.orchestrator.remove_connection("no_such_connection")

    # ── add: validation errors ─────────────────────────────────────────────

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

    def test_duplicate_connection_raises(self, two_pumps_connected: SetupWindow):
        with pytest.raises(ValueError, match="already exists"):
            two_pumps_connected.orchestrator.add_connection(
                origin="PumpA",
                destiny="PumpB",
                origin_port=2,
                destiny_port=1,
            )
