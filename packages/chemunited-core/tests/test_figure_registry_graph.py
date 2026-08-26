from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise

from chemunited_core.common.constant import R_MAX_HYDRAULIC
from chemunited_core.common.enums import ConnectionType
from chemunited_core.components import ComponentData
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_core.figure_registry import COMPONENTS
from chemunited_quantities import ChemUnitQuantity


@dataclass
class RegistryGraph:
    components: list[ComponentData]
    connections: list[EdgeData]


def _build_component(figure: str, index: int) -> ComponentData:
    data_class, mode_class = COMPONENTS[figure]
    mode = mode_class(
        name=figure,
        figure=figure,
        position=(float(index), 0.0),
        angle=0,
    )
    return data_class.from_mode(mode)


def _first_visible_ports_by_category(
    component: ComponentData,
) -> dict[ConnectionType, int]:
    ports_by_category: dict[ConnectionType, int] = {}

    for port_number, port in sorted(component.ports_by_number.items()):
        if port.show_in_graph:
            ports_by_category.setdefault(port.category, port_number)

    return ports_by_category


def build_registry_graph() -> RegistryGraph:
    components = [
        _build_component(figure, index)
        for index, figure in enumerate(COMPONENTS, start=1)
    ]
    ports_by_category: dict[ConnectionType, list[tuple[ComponentData, int]]] = {}

    for component in components:
        for category, port_number in _first_visible_ports_by_category(
            component
        ).items():
            ports_by_category.setdefault(category, []).append((component, port_number))

    connections: list[EdgeData] = []
    for category, endpoints in ports_by_category.items():
        for (origin, origin_port), (destination, destination_port) in pairwise(
            endpoints
        ):
            connections.append(
                EdgeData.from_mode(
                    EdgeMode(
                        origin=origin.name,
                        destination=destination.name,
                        origin_port=origin_port,
                        destination_port=destination_port,
                        classification=category,
                        length="100 mm",
                        diameter="1 mm",
                    )
                )
            )

    return RegistryGraph(components=components, connections=connections)


def test_figure_registry_components_build_graph() -> None:
    graph = build_registry_graph()
    component_index = {component.name: component for component in graph.components}

    assert set(component_index) == set(COMPONENTS)
    assert len(graph.components) == len(COMPONENTS)
    assert graph.connections

    for component in graph.components:
        assert component.figure == component.name
        for port_number, port in component.ports_by_number.items():
            assert port.number == port_number
            assert port.component == component.name
        for (origin, destination), internal_edge in component.internal_edges.items():
            assert internal_edge.origin_port == origin
            assert internal_edge.destination_port == destination

    for connection in graph.connections:
        origin = component_index[connection.origin]
        destination = component_index[connection.destination]

        assert connection.origin_port in origin.ports_by_number
        assert connection.destination_port in destination.ports_by_number
        assert (
            origin.ports_by_number[connection.origin_port].category
            == connection.classification
        )
        assert (
            destination.ports_by_number[connection.destination_port].category
            == connection.classification
        )


def test_solenoid_valve_2_way_common_port_is_hub() -> None:
    data_class, mode_class = COMPONENTS["SolenoidValve2Way"]
    component = data_class.from_mode(mode_class(name="divertvalve"))

    assert sorted(component.ports_by_number) == [0, 1, 2, 3]
    assert component.ports_by_number[0].is_hub is True
    assert component.ports_by_number[1].is_hub is False
    assert component.ports_by_number[2].is_hub is False
    assert component.ports_by_number[3].is_hub is False
    assert component.ports_by_number[3].category == ConnectionType.ELECTRONIC
    assert set(component.internal_edges) == {(0, 1), (0, 2)}


def test_solenoid_valve_channel_opens_and_closes_with_opened_flag() -> None:
    data_class, mode_class = COMPONENTS["SolenoidValve"]
    component = data_class.from_mode(mode_class(name="solenoid"))

    assert component.opened is True
    assert component.internal_edges[(1, 2)].resistance_override is None

    component.apply("close")
    assert component.internal_edges[(1, 2)].resistance_override == R_MAX_HYDRAULIC

    component.apply("open")
    assert component.internal_edges[(1, 2)].resistance_override is None


def test_solenoid_valve_power_on_off_respects_normally_open() -> None:
    data_class, mode_class = COMPONENTS["SolenoidValve"]

    normally_open = data_class.from_mode(
        mode_class(name="solenoid", normally_open=True)
    )
    normally_open.apply("power-on")
    assert normally_open.opened is False
    normally_open.apply("power-off")
    assert normally_open.opened is True

    normally_closed = data_class.from_mode(
        mode_class(name="solenoid", normally_open=False)
    )
    normally_closed.apply("power-on")
    assert normally_closed.opened is True
    normally_closed.apply("power-off")
    assert normally_closed.opened is False


def test_multichannel_relay_power_on_off_sets_active_flag() -> None:
    data_class, mode_class = COMPONENTS["MultiChannelRelay"]
    component = data_class.from_mode(mode_class(name="relay", channels=4))

    assert component.active == [False, False, False, False]

    component.apply("power-on", channel="2")
    assert component.active == [False, True, False, False]

    component.apply("power-off", channel="2")
    assert component.active == [False, False, False, False]


def test_multichannel_relay_multiple_channel_parses_bitstring() -> None:
    data_class, mode_class = COMPONENTS["MultiChannelRelay"]
    component = data_class.from_mode(mode_class(name="relay", channels=8))

    component.apply("multiple_channel", values="00010012")
    assert component.active == [
        False,
        False,
        False,
        True,
        False,
        False,
        True,
        True,
    ]


def test_mfc_opens_on_set_flow_rate_and_closes_on_stop() -> None:
    data_class, mode_class = COMPONENTS["MFCComponent"]
    component = data_class.from_mode(mode_class(name="mfc"))

    assert component.internal_edges[(1, 2)].resistance_override == R_MAX_HYDRAULIC

    component.apply("set-flow-rate", flowrate="1 ml/min")
    assert component.internal_edges[(1, 2)].resistance_override is None
    # MFC is a controlled variable resistance (like a valve), not a forced
    # flow source -- it must never populate forced_flow_override, which is
    # exclusive to Pump/HPLCPump.
    assert component.internal_edges[(1, 2)].forced_flow_override is None

    component.apply("stop")
    assert component.internal_edges[(1, 2)].resistance_override == R_MAX_HYDRAULIC
    assert component.internal_edges[(1, 2)].forced_flow_override is None

    component.apply("set-flow-rate", flowrate="0 ml/min")
    assert component.internal_edges[(1, 2)].resistance_override == R_MAX_HYDRAULIC
    assert component.internal_edges[(1, 2)].forced_flow_override is None


def test_hplc_pump_forces_flow_on_infuse_and_closes_on_stop() -> None:
    """Regression test for the backward-flow bug: HPLCPump must configure its
    junction edge as a hard forced-flow source the instant `infuse` is
    applied, with no dependency on solved pressures, and must return to a
    fully closed (no forced flow, no passive backflow) edge on `stop`.
    """
    data_class, mode_class = COMPONENTS["HPLCPump"]
    component = data_class.from_mode(mode_class(name="hplcpump"))

    edge = component.internal_edges[(1, 2)]
    assert edge.resistance_override == R_MAX_HYDRAULIC
    assert edge.forced_flow_override is None

    component.apply("infuse", rate="1 ml/min")
    expected_flow_si = float(ChemUnitQuantity("1 ml/min").to_base_units().magnitude)
    assert edge.resistance_override is None
    assert edge.forced_flow_override == expected_flow_si

    component.apply("stop")
    assert edge.resistance_override == R_MAX_HYDRAULIC
    assert edge.forced_flow_override is None


def test_hplc_pump_infers_finite_duration_from_volume_and_absolute_rate() -> None:
    data_class, mode_class = COMPONENTS["HPLCPump"]
    component = data_class.from_mode(mode_class(name="hplcpump"))

    result = component.apply("infuse", rate="-2 ml/min", volume="1 ml")

    assert len(result.scheduled) == 1
    assert result.scheduled[0].dt == 30.0
    assert result.scheduled[0].command == "stop"


def test_syringe_pump_infers_finite_duration_for_withdraw() -> None:
    data_class, mode_class = COMPONENTS["SyringePump"]
    component = data_class.from_mode(mode_class(name="syringepump"))

    result = component.apply("withdraw", rate="2 ml/min", volume="1 ml")

    assert len(result.scheduled) == 1
    assert result.scheduled[0].dt == 30.0
    assert result.scheduled[0].command == "stop"


def test_distribution_rotary_valves_common_port_is_hub() -> None:
    distribution_valves = [
        "TwoPortDistributionValve",
        "FourPortDistributionValve",
        "SixPortDistributionValve",
        "TwelvePortDistributionValve",
        "SixteenPortDistributionValve",
    ]

    for figure in distribution_valves:
        data_class, mode_class = COMPONENTS[figure]
        mode = mode_class(name=figure)
        component = data_class.from_mode(mode)

        assert not hasattr(mode, "ports_by_number")
        assert component.ports_by_number[0].is_hub is True
        assert all(
            port.is_hub is (port_number == 0)
            for port_number, port in component.ports_by_number.items()
        )
