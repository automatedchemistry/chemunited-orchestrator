"""Tests for adapter graph compilation details."""

from __future__ import annotations

import pytest
from chemunited_core.common.constant import ATMOSPHERE_PRESSURE_PA
from chemunited_core.common.enums import ConnectionType
from chemunited_core.components.enums import BoundaryConditionKind
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_core.figure_registry import COMPONENTS

from chemunited_sim.adapter import (
    compile_graph,
    propagate_power_links,
    resync_component,
)


def test_solenoid_valve_2_way_common_port_compiles_as_hub():
    defn = COMPONENTS["SolenoidValve2Way"]
    valve = defn.data_class.from_mode(defn.mode_class(name="divertvalve"))

    graph = compile_graph([valve], [])

    assert sorted(
        node_id for node_id in graph.nodes if node_id.startswith("divertvalve.")
    ) == ["divertvalve.0", "divertvalve.1", "divertvalve.2"]
    assert graph.nodes["divertvalve.0"].is_hub is True
    assert graph.nodes["divertvalve.1"].is_hub is False
    assert graph.nodes["divertvalve.2"].is_hub is False


def test_autosampler_vial_movement_contact_compiles_as_hydraulic_junction():
    gantry_defn = COMPONENTS["Gantry3D"]
    vial_defn = COMPONENTS["Vial"]
    gantry = gantry_defn.data_class.from_mode(
        gantry_defn.mode_class(
            name="as", position_x="1", position_y="A", position_z="DOWN"
        )
    )
    vial = vial_defn.data_class.from_mode(
        vial_defn.mode_class(name="tray", column=3, row=2, pressure_access=False)
    )
    contact = EdgeData.from_mode(
        EdgeMode(
            name="tray_1_as_2",
            origin="tray",
            origin_port=1,
            destination="as",
            destination_port=2,
            classification=ConnectionType.MOVEMENT,
        )
    )

    graph = compile_graph([gantry, vial], [contact])

    assert "as.1" in graph.nodes
    assert "as.2" in graph.nodes
    assert "tray.1" in graph.nodes
    assert "tray.A1" in graph.nodes
    assert graph.nodes["as.1"].boundary is None
    assert graph.nodes["tray.1"].boundary is not None
    assert graph.edges["as.1.2"].resistance_override is None
    assert graph.edges["as.1.3"].resistance_override is not None
    assert graph.edges["tray.1.A1"].origin_node_id == "tray.1"
    assert graph.edges["tray_1_as_2"].role.name == "JUNCTION"
    assert graph.edges["tray_1_as_2"].length == 0.0
    assert graph.edges["tray_1_as_2"].diameter == 0.0
    assert "tray.A1" in graph.inventory_nodes


def test_resync_component_updates_gantry_head_boundary():
    gantry_defn = COMPONENTS["Gantry3D"]
    gantry = gantry_defn.data_class.from_mode(
        gantry_defn.mode_class(name="as", position_z="UP")
    )
    graph = compile_graph([gantry], [])

    boundary = graph.nodes["as.1"].boundary
    assert boundary is not None
    assert boundary.kind == BoundaryConditionKind.PRESSURE
    assert boundary.value == ATMOSPHERE_PRESSURE_PA

    gantry.apply("set_z_position", position="DOWN")
    resync_component(graph, gantry)

    assert graph.nodes["as.1"].boundary is None

    gantry.apply("set_z_position", position="UP")
    resync_component(graph, gantry)

    boundary = graph.nodes["as.1"].boundary
    assert boundary is not None
    assert boundary.kind == BoundaryConditionKind.PRESSURE
    assert boundary.value == ATMOSPHERE_PRESSURE_PA


def test_hplc_pump_compiles_forced_flow_onto_its_junction_edge():
    pump_defn = COMPONENTS["HPLCPump"]
    pump = pump_defn.data_class.from_mode(pump_defn.mode_class(name="hplcpump"))
    pump.apply("infuse", rate="1 ml/min")

    graph = compile_graph([pump], [])

    edge = graph.edges["hplcpump.1.2"]
    assert edge.resistance_override is None
    assert edge.forced_flow == pytest.approx(
        pump.internal_edges[(1, 2)].forced_flow_override
    )
    assert edge.forced_flow > 0.0


def test_resync_component_propagates_pump_forced_flow():
    """Regression test for the HPLCPump backward-flow bug's second cause:
    resync_component() must propagate forced_flow (not just
    resistance_override), or the very next solve after a command sees a
    stale/None forced_flow on an already-open edge.
    """
    pump_defn = COMPONENTS["HPLCPump"]
    pump = pump_defn.data_class.from_mode(pump_defn.mode_class(name="hplcpump"))
    graph = compile_graph([pump], [])

    edge = graph.edges["hplcpump.1.2"]
    assert edge.resistance_override is not None
    assert edge.forced_flow is None

    pump.apply("infuse", rate="2 ml/min")
    resync_component(graph, pump)

    assert edge.resistance_override is None
    assert edge.forced_flow == pytest.approx(
        pump.internal_edges[(1, 2)].forced_flow_override
    )
    assert edge.forced_flow > 0.0

    pump.apply("stop")
    resync_component(graph, pump)

    assert edge.resistance_override is not None
    assert edge.forced_flow is None


def test_heat_connection_compiles_as_heat_link_not_hydraulic_edge():
    controller_defn = COMPONENTS["TemperatureControl"]
    vessel_defn = COMPONENTS["GlassBottle"]
    controller = controller_defn.data_class.from_mode(
        controller_defn.mode_class(name="chiller")
    )
    vessel = vessel_defn.data_class.from_mode(
        vessel_defn.mode_class(name="reactor", heat_exchange=True)
    )
    edge = EdgeData.from_mode(
        EdgeMode(
            name="thermal_link",
            origin="chiller",
            origin_port=1,
            destination="reactor",
            destination_port=2,
            classification=ConnectionType.HEAT,
        )
    )

    graph = compile_graph([controller, vessel], [edge])

    assert len(graph.heat_links) == 1
    link = graph.heat_links[0]
    assert link.provider_component == "chiller"
    assert link.provider_port == 1
    assert link.target_component == "reactor"
    assert link.target_port == 2
    assert "thermal_link" not in graph.edges
    assert "chiller.1" not in graph.nodes


def test_heat_connection_rejects_non_heat_endpoint():
    controller_defn = COMPONENTS["TemperatureControl"]
    vessel_defn = COMPONENTS["GlassBottle"]
    controller = controller_defn.data_class.from_mode(
        controller_defn.mode_class(name="chiller")
    )
    vessel = vessel_defn.data_class.from_mode(
        vessel_defn.mode_class(name="reactor", heat_exchange=True)
    )
    edge = EdgeData.from_mode(
        EdgeMode(
            name="bad_thermal_link",
            origin="chiller",
            origin_port=1,
            destination="reactor",
            destination_port=1,
            classification=ConnectionType.HEAT,
        )
    )

    with pytest.raises(ValueError, match="not a HEAT port"):
        compile_graph([controller, vessel], [edge])


def _electronic_edge(
    name: str, origin: str, origin_port, destination: str, destination_port
) -> EdgeData:
    return EdgeData.from_mode(
        EdgeMode(
            name=name,
            origin=origin,
            origin_port=origin_port,
            destination=destination,
            destination_port=destination_port,
            classification=ConnectionType.ELECTRONIC,
        )
    )


def test_power_connection_compiles_as_power_link_not_hydraulic_edge():
    relay_defn = COMPONENTS["MultiChannelRelay"]
    valve_defn = COMPONENTS["SolenoidValve"]
    relay = relay_defn.data_class.from_mode(relay_defn.mode_class(name="relay"))
    valve = valve_defn.data_class.from_mode(valve_defn.mode_class(name="solenoid"))
    edge = _electronic_edge("power_link", "relay", 1, "solenoid", 3)

    graph = compile_graph([relay, valve], [edge])

    assert len(graph.power_links) == 1
    link = graph.power_links[0]
    assert link.provider_component == "relay"
    assert link.provider_port == 1
    assert link.target_component == "solenoid"
    assert link.target_port == 3
    assert "power_link" not in graph.edges
    assert "relay.1" not in graph.nodes


def test_power_connection_fan_out_to_multiple_targets():
    relay_defn = COMPONENTS["MultiChannelRelay"]
    valve_defn = COMPONENTS["SolenoidValve"]
    relay = relay_defn.data_class.from_mode(relay_defn.mode_class(name="relay"))
    valve_a = valve_defn.data_class.from_mode(valve_defn.mode_class(name="valvea"))
    valve_b = valve_defn.data_class.from_mode(valve_defn.mode_class(name="valveb"))
    edge_a = _electronic_edge("link_a", "relay", 1, "valvea", 3)
    edge_b = _electronic_edge("link_b", "relay", 1, "valveb", 3)

    graph = compile_graph([relay, valve_a, valve_b], [edge_a, edge_b])

    assert len(graph.power_links) == 2
    assert {link.target_component for link in graph.power_links} == {
        "valvea",
        "valveb",
    }
    assert all(link.provider_port == 1 for link in graph.power_links)


def test_power_connection_rejects_second_provider_for_same_target():
    relay_defn = COMPONENTS["MultiChannelRelay"]
    valve_defn = COMPONENTS["SolenoidValve"]
    relay_a = relay_defn.data_class.from_mode(relay_defn.mode_class(name="relaya"))
    relay_b = relay_defn.data_class.from_mode(relay_defn.mode_class(name="relayb"))
    valve = valve_defn.data_class.from_mode(valve_defn.mode_class(name="solenoid"))
    edge_a = _electronic_edge("link_a", "relaya", 1, "solenoid", 3)
    edge_b = _electronic_edge("link_b", "relayb", 1, "solenoid", 3)

    with pytest.raises(ValueError, match="multiple electronic providers"):
        compile_graph([relay_a, relay_b, valve], [edge_a, edge_b])


def test_power_connection_rejects_non_electronic_endpoint():
    relay_defn = COMPONENTS["MultiChannelRelay"]
    valve_defn = COMPONENTS["SolenoidValve"]
    relay = relay_defn.data_class.from_mode(relay_defn.mode_class(name="relay"))
    valve = valve_defn.data_class.from_mode(valve_defn.mode_class(name="solenoid"))
    edge = _electronic_edge("bad_power_link", "relay", 1, "solenoid", 1)

    with pytest.raises(ValueError, match="not an ELECTRONIC port"):
        compile_graph([relay, valve], [edge])


def test_power_connection_rejects_relay_to_adc_miswiring():
    relay_defn = COMPONENTS["MultiChannelRelay"]
    adc_defn = COMPONENTS["MultiChannelADC"]
    relay = relay_defn.data_class.from_mode(relay_defn.mode_class(name="relay"))
    adc = adc_defn.data_class.from_mode(adc_defn.mode_class(name="adc"))
    edge = _electronic_edge("bad_power_link", "relay", 1, "adc", 1)

    with pytest.raises(ValueError, match="must connect exactly one relay channel"):
        compile_graph([relay, adc], [edge])


def test_propagate_power_links_energizes_and_deenergizes_target():
    relay_defn = COMPONENTS["MultiChannelRelay"]
    valve_defn = COMPONENTS["SolenoidValve"]
    relay = relay_defn.data_class.from_mode(relay_defn.mode_class(name="relay"))
    valve = valve_defn.data_class.from_mode(
        valve_defn.mode_class(name="solenoid", normally_open=True)
    )
    edge = _electronic_edge("power_link", "relay", 1, "solenoid", 3)
    graph = compile_graph([relay, valve], [edge])
    components_by_name = {"relay": relay, "solenoid": valve}
    cache: dict[tuple[str, int], bool] = {}

    calls: list[str] = []
    original_apply = valve.apply

    def _spy_apply(command, **kwargs):
        calls.append(command)
        return original_apply(command, **kwargs)

    valve.apply = _spy_apply

    relay.apply("power-on", channel="1")
    propagate_power_links(relay, graph, components_by_name, cache)

    assert valve.opened is False
    assert graph.edges["solenoid.1.2"].resistance_override is not None
    assert calls == ["power-on"]

    # Repeating the same command is a no-op transition: propagate_power_links
    # must not re-invoke the target's apply().
    relay.apply("power-on", channel="1")
    propagate_power_links(relay, graph, components_by_name, cache)
    assert calls == ["power-on"]

    relay.apply("power-off", channel="1")
    propagate_power_links(relay, graph, components_by_name, cache)
    assert valve.opened is True
    assert graph.edges["solenoid.1.2"].resistance_override is None
    assert calls == ["power-on", "power-off"]


def test_propagate_power_links_leaves_unlinked_target_untouched():
    relay_defn = COMPONENTS["MultiChannelRelay"]
    valve_defn = COMPONENTS["SolenoidValve"]
    relay = relay_defn.data_class.from_mode(relay_defn.mode_class(name="relay"))
    valve = valve_defn.data_class.from_mode(valve_defn.mode_class(name="solenoid"))
    graph = compile_graph([relay, valve], [])
    components_by_name = {"relay": relay, "solenoid": valve}

    relay.apply("power-on", channel="1")
    propagate_power_links(relay, graph, components_by_name, {})

    assert valve.opened is True
