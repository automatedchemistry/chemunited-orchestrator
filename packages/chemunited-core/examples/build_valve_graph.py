from __future__ import annotations

# ruff: noqa: E402
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from chemunited_core.common.enums import ConnectionType
from chemunited_core.components import (
    BackPressureRegulatorData,
    BackPressureRegulatorMode,
    ComponentData,
    FlowSourceData,
    FlowSourceMode,
    JunctionData,
    JunctionMode,
    PlugFlowComponentData,
    PlugFlowMode,
    PressureControlData,
    PressureControlMode,
    ValveComponentData,
    ValveMode,
    VesselComponentData,
    VesselMode,
)
from chemunited_core.connections import EdgeData, EdgeMode

OUTPUT_HTML = Path(__file__).resolve().parent / "output" / "valve_flow_graph.html"
POSITION_SCALE = 220


@dataclass
class ExampleGraph:
    components: list[ComponentData]
    connections: list[EdgeData]


def build_example_graph() -> ExampleGraph:
    flow_source = FlowSourceData.from_mode(
        FlowSourceMode(
            name="FeedPump",
            figure="PumpFigure",
            position=(-2.0, 0.0),
            angle=0,
            flow_rate="5 ml/min",
        )
    )
    pressure_control = PressureControlData.from_mode(
        PressureControlMode(
            name="GasLine",
            figure="PressureFigure",
            position=(0.0, -2.0),
            angle=0,
            setpoint="1.2 bar",
        )
    )
    feed_vessel = VesselComponentData.from_mode(
        VesselMode(
            name="FeedVessel",
            figure="FlaskFigure",
            position=(0.0, 0.0),
            angle=0,
            capacity="250 ml",
            top_access=3,
            bottom_access=2,
        )
    )
    junction = JunctionData.from_mode(
        JunctionMode(
            name="MixerJunction",
            figure="JunctionFigure",
            position=(2.0, 0.0),
            angle=0,
            number_ports=3,
        )
    )
    selector_valve = ValveComponentData.from_mode(
        ValveMode(
            name="SelectorValve",
            figure="ValveFigure",
            position=(4.0, 0.0),
            angle=0,
        )
    )
    reactor = PlugFlowComponentData.from_mode(
        PlugFlowMode(
            name="ReactorTube",
            figure="TubeFigure",
            position=(6.0, 0.0),
            angle=0,
            length="500 mm",
            diameter="2 mm",
        )
    )
    pressure_regulator = BackPressureRegulatorData.from_mode(
        BackPressureRegulatorMode(
            name="OutletBPR",
            figure="BprFigure",
            position=(8.0, 0.0),
            angle=0,
            setpoint="1.5 bar",
        )
    )
    product_vessel = VesselComponentData.from_mode(
        VesselMode(
            name="ProductVessel",
            figure="FlaskFigure",
            position=(10.0, 1.0),
            angle=0,
            capacity="250 ml",
            top_access=3,
            bottom_access=2,
        )
    )
    waste_vessel = VesselComponentData.from_mode(
        VesselMode(
            name="WasteVessel",
            figure="FlaskFigure",
            position=(10.0, -1.0),
            angle=0,
            capacity="250 ml",
            top_access=3,
            bottom_access=2,
        )
    )

    connections = [
        EdgeData.from_mode(
            EdgeMode(
                origin=flow_source.name,
                destination=feed_vessel.name,
                origin_port=1,
                destination_port=1,
                length="80 mm",
                diameter="1.6 mm",
            )
        ),
        EdgeData.from_mode(
            EdgeMode(
                origin=pressure_control.name,
                destination=feed_vessel.name,
                origin_port=1,
                destination_port=5,
                length="60 mm",
                diameter="1.0 mm",
            )
        ),
        EdgeData.from_mode(
            EdgeMode(
                origin=feed_vessel.name,
                destination=junction.name,
                origin_port=1,
                destination_port=1,
                length="120 mm",
                diameter="1.6 mm",
            )
        ),
        EdgeData.from_mode(
            EdgeMode(
                origin=junction.name,
                destination=selector_valve.name,
                origin_port=2,
                destination_port=0,
                length="80 mm",
                diameter="1.6 mm",
            )
        ),
        EdgeData.from_mode(
            EdgeMode(
                origin=junction.name,
                destination=waste_vessel.name,
                origin_port=3,
                destination_port=1,
                length="140 mm",
                diameter="1.6 mm",
            )
        ),
        EdgeData.from_mode(
            EdgeMode(
                origin=selector_valve.name,
                destination=reactor.name,
                origin_port=1,
                destination_port=1,
                length="90 mm",
                diameter="1.6 mm",
            )
        ),
        EdgeData.from_mode(
            EdgeMode(
                origin=reactor.name,
                destination=pressure_regulator.name,
                origin_port=2,
                destination_port=1,
                length="90 mm",
                diameter="1.6 mm",
            )
        ),
        EdgeData.from_mode(
            EdgeMode(
                origin=pressure_regulator.name,
                destination=product_vessel.name,
                origin_port=2,
                destination_port=1,
                length="120 mm",
                diameter="1.6 mm",
            )
        ),
        EdgeData.from_mode(
            EdgeMode(
                origin=selector_valve.name,
                destination=waste_vessel.name,
                origin_port=6,
                destination_port=2,
                length="120 mm",
                diameter="1.6 mm",
            )
        ),
    ]

    return ExampleGraph(
        components=[
            flow_source,
            pressure_control,
            feed_vessel,
            junction,
            selector_valve,
            reactor,
            pressure_regulator,
            product_vessel,
            waste_vessel,
        ],
        connections=connections,
    )


def _component_color(component: ComponentData) -> str:
    if isinstance(component, FlowSourceData):
        return "#dc2626"
    if isinstance(component, PressureControlData):
        return "#7c3aed"
    if isinstance(component, BackPressureRegulatorData):
        return "#ea580c"
    if isinstance(component, JunctionData):
        return "#0891b2"
    if isinstance(component, VesselComponentData):
        return "#0f766e"
    if isinstance(component, ValveComponentData):
        return "#b45309"
    if isinstance(component, PlugFlowComponentData):
        return "#1d4ed8"
    return "#475569"


def _port_node_id(component_name: str, port_number: int | str) -> str:
    return f"{component_name}.{port_number}"


def _inventory_node_id(component_name: str) -> str:
    return f"{component_name}.Inventory"


def _visible_flow_ports(component: ComponentData):
    return [
        (number, port)
        for number, port in sorted(component.ports_by_number.items())
        if port.category == ConnectionType.HYDRAULIC
    ]


def _visible_flow_port_numbers(component: ComponentData) -> list[int]:
    return [number for number, _ in _visible_flow_ports(component)]


def _port_positions(component: ComponentData) -> dict[int, tuple[float, float]]:
    positions: dict[int, tuple[float, float]] = {}
    component_x, component_y = component.position

    for port_number, port in _visible_flow_ports(component):
        scene_x = component_x + port.relative_position[0]
        scene_y = component_y + port.relative_position[1]
        positions[port_number] = (
            scene_x * POSITION_SCALE,
            scene_y * POSITION_SCALE,
        )

    return positions


def _port_title(component: ComponentData, port_number: int) -> str:
    port = component.ports_by_number[port_number]
    return "<br>".join(
        [
            f"{component.name}.{port.number}",
            f"component: {component.name}",
            f"type: {type(component).__name__}",
            f"category: {port.category.value}",
            f"access: {port.access.name.lower()}",
            f"closure: {port.closure.name.lower()}",
            (
                "boundary: " f"{port.boundary.kind.name.lower()}={port.boundary.value}"
                if port.boundary is not None
                else "boundary: none"
            ),
            f"relative position: {port.relative_position}",
            f"scene position: ({component.position[0] + port.relative_position[0]}, "
            f"{component.position[1] + port.relative_position[1]})",
        ]
    )


def _inventory_title(component: ComponentData) -> str:
    inventory = component.internal_inventory
    if inventory is None:
        return f"{component.name}.Inventory"

    return "<br>".join(
        [
            f"{component.name}.Inventory",
            f"gas volume: {inventory.gas_content.volume}",
            f"liquid volume: {inventory.liq_content.volume}",
        ]
    )


def export_pyvis_html(
    graph: ExampleGraph, output_path: Path = OUTPUT_HTML
) -> Path | None:
    try:
        from pyvis.network import Network
    except ImportError:
        return None

    output_path.parent.mkdir(parents=True, exist_ok=True)
    network = Network(height="700px", width="100%", directed=True, bgcolor="#ffffff")
    network.toggle_physics(False)
    component_index = {component.name: component for component in graph.components}

    for component in graph.components:
        component_color = _component_color(component)
        port_positions = _port_positions(component)
        visible_ports = set(port_positions)

        for port_number, (x_position, y_position) in port_positions.items():
            network.add_node(
                _port_node_id(component.name, port_number),
                label=f"{component.name}.{port_number}",
                title=_port_title(component, port_number),
                shape="dot",
                size=18,
                color=component_color,
                x=x_position,
                y=y_position,
                physics=False,
            )

        show_inventory = component.internal_inventory is not None and any(
            origin in visible_ports and isinstance(destination, str)
            for origin, destination in component.internal_edges
        )

        if show_inventory:
            base_x = component.position[0] * POSITION_SCALE
            base_y = component.position[1] * POSITION_SCALE
            network.add_node(
                _inventory_node_id(component.name),
                label=f"{component.name}.Inventory",
                title=_inventory_title(component),
                shape="diamond",
                size=26,
                color="#f59e0b",
                x=base_x,
                y=base_y,
                physics=False,
            )

        for (origin, destination), internal_edge in component.internal_edges.items():
            if origin not in visible_ports:
                continue

            if isinstance(destination, str):
                if not show_inventory:
                    continue
                destination_id = _inventory_node_id(component.name)
            else:
                if destination not in visible_ports:
                    continue
                destination_id = _port_node_id(component.name, destination)

            network.add_edge(
                _port_node_id(component.name, origin),
                destination_id,
                title=(
                    f"{component.name}: {origin} -> {destination}<br>"
                    f"role: {internal_edge.role.name.lower()}<br>"
                    f"active: {internal_edge.is_active}<br>"
                    f"length: {internal_edge.length}<br>"
                    f"diameter: {internal_edge.diameter}"
                ),
                color=component_color,
                dashes=not internal_edge.is_active,
                width=3 if internal_edge.is_active else 1.5,
                arrows="to",
            )

    for connection in graph.connections:
        origin_component = component_index[connection.origin]
        destination_component = component_index[connection.destination]
        if connection.origin_port not in _visible_flow_port_numbers(
            origin_component
        ) or connection.destination_port not in _visible_flow_port_numbers(
            destination_component
        ):
            continue

        network.add_edge(
            _port_node_id(connection.origin, connection.origin_port),
            _port_node_id(connection.destination, connection.destination_port),
            label=f"{connection.origin_port} -> {connection.destination_port}",
            title=(
                f"{connection.name}<br>"
                f"classification: {connection.classification.value}<br>"
                f"length: {connection.length}<br>"
                f"diameter: {connection.diameter}"
            ),
            color="#334155",
            arrows="to",
        )

    if hasattr(network, "write_html"):
        network.write_html(str(output_path), open_browser=False, notebook=False)
    else:
        network.save_graph(str(output_path))

    return output_path


def main():
    graph = build_example_graph()
    component_index = {component.name: component for component in graph.components}
    visible_process_connections = [
        connection
        for connection in graph.connections
        if connection.origin_port
        in _visible_flow_port_numbers(component_index[connection.origin])
        and connection.destination_port
        in _visible_flow_port_numbers(component_index[connection.destination])
    ]
    port_count = sum(
        len(_visible_flow_port_numbers(component)) for component in graph.components
    )
    internal_node_count = sum(
        1
        for component in graph.components
        if component.internal_inventory is not None
        and any(
            origin in _visible_flow_port_numbers(component)
            and isinstance(destination, str)
            for origin, destination in component.internal_edges
        )
    )
    internal_edge_count = sum(
        1
        for component in graph.components
        for (origin, destination) in component.internal_edges
        if origin in _visible_flow_port_numbers(component)
        and (
            isinstance(destination, str)
            or destination in _visible_flow_port_numbers(component)
        )
    )
    print(
        f"Built example graph with {port_count} hydraulic port nodes, "
        f"{internal_node_count} internal nodes, "
        f"{internal_edge_count} internal edges, and "
        f"{len(visible_process_connections)} process connections."
    )

    for component in graph.components:
        port_numbers = _visible_flow_port_numbers(component)
        print(
            f"- {component.name}: {type(component).__name__} "
            f"hydraulic_ports={port_numbers} "
            f"inventory={component.internal_inventory is not None} "
            f"internal_edges={len(component.internal_edges)}"
        )

    html_path = export_pyvis_html(graph)
    if html_path is None:
        print("pyvis is not installed; skipped HTML export.")
    else:
        print(f"Pyvis HTML written to {html_path}")


if __name__ == "__main__":
    main()
