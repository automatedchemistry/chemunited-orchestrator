"""Tests for the design-time hydraulic port open/close (cap) toggle.

What is tested:
- GraphComponent.set_port_closed mutates the core Port.closure and the
  ConnectionPoint's visual "capped" state together
- Toggling back to open restores both
- The capped state is included in _build_draw_data()'s "port_closures" payload
  and removed once the port is reopened
- The capped state survives a full save/restore round trip via
  _restore_draw_data()
"""

import pytest
from pytestqt.qtbot import QtBot

from chemunited.setup import SetupWindow
from chemunited_core.components.enums import PortClosure

PORT_NUM = 2


class TestPortClosure:

    @pytest.fixture
    def window(self, qtbot: QtBot):
        w = SetupWindow()
        qtbot.addWidget(w)
        w.show()
        qtbot.waitExposed(w)
        return w

    @pytest.fixture
    def pump(self, window: SetupWindow):
        """Window with a single HPLCPump component (hydraulic ports 1 & 2)."""
        window.orchestrator.add_component(
            name="PumpA", figure="HPLCPump", position=(0.0, 0.0)
        )
        return window.orchestrator.components["PumpA"]

    # ── toggle mechanics ────────────────────────────────────────────────────

    def test_set_port_closed_caps_the_port(self, pump):
        pump.graph.set_port_closed(PORT_NUM, True)

        assert pump.inf.ports_by_number[PORT_NUM].closure == PortClosure.CAPPED
        assert pump.graph.get_connection_point(PORT_NUM).is_capped is True

    def test_set_port_closed_reopens_the_port(self, pump):
        pump.graph.set_port_closed(PORT_NUM, True)
        pump.graph.set_port_closed(PORT_NUM, False)

        assert pump.inf.ports_by_number[PORT_NUM].closure == PortClosure.OPEN
        assert pump.graph.get_connection_point(PORT_NUM).is_capped is False

    def test_ports_are_open_by_default(self, pump):
        assert pump.inf.ports_by_number[PORT_NUM].closure == PortClosure.OPEN
        assert pump.graph.get_connection_point(PORT_NUM).is_capped is False

    # ── in-memory persistence (project_file.py) ─────────────────────────────

    def test_capped_port_is_in_draw_data_payload(self, window: SetupWindow, pump):
        pump.graph.set_port_closed(PORT_NUM, True)

        draw_data = window.orchestrator._build_draw_data()

        assert draw_data["port_closures"] == {"PumpA": {str(PORT_NUM): True}}

    def test_reopened_port_is_removed_from_draw_data_payload(
        self, window: SetupWindow, pump
    ):
        pump.graph.set_port_closed(PORT_NUM, True)
        pump.graph.set_port_closed(PORT_NUM, False)

        draw_data = window.orchestrator._build_draw_data()

        assert draw_data.get("port_closures", {}) == {}

    def test_deleting_capped_component_removes_it_from_draw_data_payload(
        self, window: SetupWindow, pump
    ):
        pump.graph.set_port_closed(PORT_NUM, True)
        window.orchestrator.remove_component("PumpA")

        draw_data = window.orchestrator._build_draw_data()

        assert draw_data.get("port_closures", {}) == {}

    # ── full save/restore round trip ────────────────────────────────────────

    def test_capped_port_survives_restore_draw_data(self, window: SetupWindow, pump):
        pump.graph.set_port_closed(PORT_NUM, True)
        draw_data = window.orchestrator._build_draw_data()

        window.orchestrator.remove_component("PumpA")
        window.orchestrator._restore_draw_data(draw_data)

        restored = window.orchestrator.components["PumpA"]
        assert restored.inf.ports_by_number[PORT_NUM].closure == PortClosure.CAPPED
        assert restored.graph.get_connection_point(PORT_NUM).is_capped is True
