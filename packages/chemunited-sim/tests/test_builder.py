"""Tests for PlatformBuilder: capped ports and LCD displays written by draw/setup.py."""

from __future__ import annotations

from chemunited_core.components.enums import PortClosure
from chemunited_sim.adapter.graph import compile_graph
from chemunited_sim.cli.builder import PlatformBuilder


def test_set_port_closed_caps_the_port_and_drops_it_from_the_graph() -> None:
    builder = PlatformBuilder()
    builder.add_component(name="V", figure="SixPortDistributionValve")

    builder.set_port_closed(component="V", port=2)

    assert builder["V"].ports_by_number[2].closure == PortClosure.CAPPED
    graph = compile_graph(builder.components, builder.edges)
    assert "V.2" not in graph.nodes
    assert "V.3" in graph.nodes


def test_set_port_closed_can_reopen_and_ignores_unknown_ports() -> None:
    builder = PlatformBuilder()
    builder.add_component(name="V", figure="SixPortDistributionValve")

    builder.set_port_closed(component="V", port=2)
    builder.set_port_closed(component="V", port=2, closed=False)
    builder.set_port_closed(component="V", port=99)
    builder.set_port_closed(component="missing", port=1)

    assert builder["V"].ports_by_number[2].closure == PortClosure.OPEN


def test_add_display_is_accepted_and_adds_nothing_to_simulate() -> None:
    builder = PlatformBuilder()
    builder.add_component(name="V", figure="SixPortDistributionValve")

    builder.add_display(
        name="Inlet pressure",
        position=(0.0, 0.0),
        component="V",
        command="monitor_position",
        kwargs={},
    )

    assert [component.name for component in builder.components] == ["V"]
    assert builder.edges == []
