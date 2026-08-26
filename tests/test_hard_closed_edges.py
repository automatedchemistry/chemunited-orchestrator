"""Regression tests for logically hard-closed hydraulic edges."""

from __future__ import annotations

from collections import deque
from dataclasses import replace

import pytest
from chemunited_core.common.constant import (
    ATMOSPHERE_PRESSURE_PA,
    R_MAX_HYDRAULIC,
)
from chemunited_core.common.enums import PhaseKind
from chemunited_core.components.enums import BoundaryConditionKind, InternalEdgeRole
from chemunited_core.components.internals import PortBoundaryCondition
from chemunited_core.figure_registry import (
    SixPortTwoPositionValveData,
    SixPortTwoPositionValveMode,
)

from chemunited_sim.adapter.graph import compile_graph
from chemunited_sim.adapter.models import HydraulicEdge, HydraulicGraph, HydraulicNode
from chemunited_sim.hydraulics import solve
from chemunited_sim.hydraulics.models import HydraulicState
from chemunited_sim.transport.engine import advance
from chemunited_sim.transport.models import Pocket, TransportState


def _node(
    node_id: str,
    boundary: PortBoundaryCondition | None = None,
) -> HydraulicNode:
    return HydraulicNode(
        node_id=node_id,
        boundary=boundary,
        is_hub=False,
        component=node_id.split(".")[0],
    )


def _edge(
    edge_id: str,
    origin: str,
    destination: str,
    *,
    role: InternalEdgeRole = InternalEdgeRole.TRANSPORT,
    resistance_override: float | None = None,
) -> HydraulicEdge:
    return HydraulicEdge(
        edge_id=edge_id,
        origin_node_id=origin,
        destination_node_id=destination,
        length=0.02,
        diameter=0.001 if role == InternalEdgeRole.TRANSPORT else 0.0,
        role=role,
        resistance_override=resistance_override,
        component=None,
        is_external=role == InternalEdgeRole.TRANSPORT,
    )


def _pressure(value: float) -> PortBoundaryCondition:
    return PortBoundaryCondition(BoundaryConditionKind.PRESSURE, value)


def test_closed_edge_has_zero_flow_and_reopens_without_recompile() -> None:
    graph = HydraulicGraph()
    graph.nodes["source"] = _node("source", _pressure(300_000.0))
    graph.nodes["sink"] = _node("sink", _pressure(100_000.0))
    graph.edges["valve"] = _edge(
        "valve",
        "source",
        "sink",
        role=InternalEdgeRole.JUNCTION,
        resistance_override=R_MAX_HYDRAULIC,
    )

    closed_state = solve(graph)
    assert closed_state.flows["valve"] == 0.0

    graph.edges["valve"].resistance_override = None
    open_state = solve(graph)
    assert open_state.flows["valve"] > 0.0


def test_closed_edge_splits_and_anchors_pressure_components() -> None:
    graph = HydraulicGraph()
    graph.nodes["source"] = _node("source", _pressure(300_000.0))
    graph.nodes["isolated.1"] = _node("isolated.1")
    graph.nodes["isolated.2"] = _node("isolated.2")
    graph.edges["closed"] = _edge(
        "closed",
        "source",
        "isolated.1",
        role=InternalEdgeRole.JUNCTION,
        resistance_override=R_MAX_HYDRAULIC,
    )
    graph.edges["isolated"] = _edge("isolated", "isolated.1", "isolated.2")

    state = solve(graph)

    assert state.flows["closed"] == 0.0
    assert state.pressures["isolated.1"] == pytest.approx(ATMOSPHERE_PRESSURE_PA)
    assert state.pressures["isolated.2"] == pytest.approx(ATMOSPHERE_PRESSURE_PA)


def test_six_port_valve_closed_pairs_have_exactly_zero_flow() -> None:
    valve = SixPortTwoPositionValveData.from_mode(
        SixPortTwoPositionValveMode(name="AS-D")
    )
    valve.apply("position", connect=[1, 2])
    graph = compile_graph([valve], [])

    for port_number in range(1, 7):
        node_id = f"AS-D.{port_number}"
        graph.nodes[node_id] = replace(
            graph.nodes[node_id],
            boundary=_pressure(100_000.0 + port_number * 10_000.0),
        )

    state = solve(graph)

    for pair in ((1, 2), (3, 4), (5, 6)):
        assert state.flows[f"AS-D.{pair[0]}.{pair[1]}"] != 0.0
    for pair in ((1, 6), (2, 3), (4, 5)):
        assert state.flows[f"AS-D.{pair[0]}.{pair[1]}"] == 0.0


def test_as_d_pocket_ignores_closed_shortcut_and_enters_loop() -> None:
    graph = HydraulicGraph()
    for node_id in ("head", "AS-D.4", "AS-D.3", "AS-D.2", "loop.2"):
        graph.nodes[node_id] = _node(node_id)
    graph.edges["head_to_4"] = _edge("head_to_4", "head", "AS-D.4")
    graph.edges["AS-D.3.4"] = _edge(
        "AS-D.3.4",
        "AS-D.3",
        "AS-D.4",
        role=InternalEdgeRole.JUNCTION,
    )
    graph.edges["AS-D.2.3"] = _edge(
        "AS-D.2.3",
        "AS-D.2",
        "AS-D.3",
        role=InternalEdgeRole.JUNCTION,
        resistance_override=R_MAX_HYDRAULIC,
    )
    graph.edges["loop_to_3"] = _edge("loop_to_3", "loop.2", "AS-D.3")

    pocket = Pocket(
        phase_kind=PhaseKind.LIQUID,
        volume=1.0e-6,
        species_moles={"HeavyWater": 0.05},
        temperature=298.0,
        pressure=ATMOSPHERE_PRESSURE_PA,
    )
    transport_state = TransportState(
        edge_queues={
            "head_to_4": deque([pocket]),
            "loop_to_3": deque(),
        }
    )
    hydraulic_state = HydraulicState(
        pressures={},
        flows={
            "head_to_4": 1.0e-5,
            "AS-D.3.4": -1.0e-5,
            "AS-D.2.3": -1.0e-11,
            "loop_to_3": -1.0e-5,
        },
    )

    result = advance(graph, hydraulic_state, transport_state, dt=0.1)

    routed = list(result.next_state.edge_queues["loop_to_3"])
    assert len(routed) == 1
    assert routed[0].species_moles == pytest.approx(pocket.species_moles)
