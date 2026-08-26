"""Tests for transport pocket routing."""

from __future__ import annotations

import math
from collections import deque

import pytest
from chemunited_core.common.constant import R_MAX_HYDRAULIC
from chemunited_core.common.enums import PhaseKind
from chemunited_core.components.enums import InternalEdgeRole
from chemunited_core.compounds import COMPOUNDS

from chemunited_sim.adapter.models import HydraulicEdge, HydraulicGraph, HydraulicNode
from chemunited_sim.hydraulics.models import HydraulicState
from chemunited_sim.transport.engine import (
    TransportHeatExchangeEntry,
    advance,
    apply_transport_heat_exchange,
    inject,
)
from chemunited_sim.transport.models import Pocket, TransportState


def _node(node_id: str, *, is_hub: bool = False) -> HydraulicNode:
    return HydraulicNode(
        node_id=node_id,
        boundary=None,
        is_hub=is_hub,
        component=None,
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
        length=1.0,
        diameter=1.0e-3 if role == InternalEdgeRole.TRANSPORT else 0.0,
        role=role,
        resistance_override=resistance_override,
        component=None,
        is_external=role == InternalEdgeRole.TRANSPORT,
    )


def _hot_pocket(volume: float = 1.0e-6) -> Pocket:
    return Pocket(
        phase_kind=PhaseKind.LIQUID,
        volume=volume,
        species_moles={"tracer": 2.0},
        temperature=315.0,
        pressure=123_456.0,
    )


def _bpr_like_graph() -> HydraulicGraph:
    graph = HydraulicGraph()
    for node_id in ("src", "bpr.1", "bpr.2", "sink"):
        graph.nodes[node_id] = _node(node_id)
    graph.edges["upstream"] = _edge("upstream", "src", "bpr.1")
    graph.edges["bpr.1.2"] = _edge(
        "bpr.1.2",
        "bpr.1",
        "bpr.2",
        role=InternalEdgeRole.JUNCTION,
    )
    graph.edges["downstream"] = _edge("downstream", "bpr.2", "sink")
    return graph


def test_non_hub_pass_through_routes_pocket_to_downstream_transport() -> None:
    graph = _bpr_like_graph()
    pocket = _hot_pocket()
    state = TransportState(
        edge_queues={
            "upstream": deque([pocket]),
            "downstream": deque(),
        }
    )
    hyd_state = HydraulicState(
        pressures={},
        flows={
            "upstream": 1.0e-5,
            "bpr.1.2": 1.0e-5,
            "downstream": 1.0e-5,
        },
    )

    result = advance(graph, hyd_state, state, dt=0.1)

    assert result.arrivals == {}
    assert list(result.next_state.edge_queues["upstream"]) == []
    routed = list(result.next_state.edge_queues["downstream"])
    assert len(routed) == 1
    assert routed[0].phase_kind == PhaseKind.LIQUID
    assert routed[0].volume == pytest.approx(pocket.volume)
    assert routed[0].species_moles == pytest.approx(pocket.species_moles)
    assert routed[0].temperature == pytest.approx(315.0)
    assert routed[0].pressure == pytest.approx(123_456.0)


def test_reverse_non_hub_pass_through_injects_at_destination_end() -> None:
    graph = _bpr_like_graph()
    hot = _hot_pocket()
    cold = Pocket(
        phase_kind=PhaseKind.LIQUID,
        volume=2.0e-6,
        species_moles={"carrier": 1.0},
        temperature=298.15,
        pressure=101_325.0,
    )
    state = TransportState(
        edge_queues={
            "upstream": deque([cold]),
            "downstream": deque([hot]),
        }
    )
    hyd_state = HydraulicState(
        pressures={},
        flows={
            "upstream": -1.0e-5,
            "bpr.1.2": -1.0e-5,
            "downstream": -1.0e-5,
        },
    )

    result = advance(graph, hyd_state, state, dt=0.1)

    upstream = list(result.next_state.edge_queues["upstream"])
    assert len(upstream) == 2
    assert upstream[0].temperature == pytest.approx(315.0)
    assert upstream[0].species_moles == pytest.approx(hot.species_moles)
    assert upstream[1].temperature == pytest.approx(298.15)
    assert upstream[1].volume == pytest.approx(1.0e-6)
    assert list(result.next_state.edge_queues["downstream"]) == []


def _valve_common_port_graph() -> HydraulicGraph:
    """Mirror a rotary distribution valve's common port: `hub` is both the
    hub node and the direct attachment point of a TRANSPORT edge (like
    SixPortDistributionValve.0 -> SyringePump), reached from `src` via a
    peripheral port and a JUNCTION channel (like GlassBottle -> port 1)."""
    graph = HydraulicGraph()
    for node_id in ("src", "port1", "hub", "dst"):
        graph.nodes[node_id] = _node(node_id, is_hub=(node_id == "hub"))
    graph.edges["upstream"] = _edge("upstream", "src", "port1")
    graph.edges["port1.hub"] = _edge(
        "port1.hub", "port1", "hub", role=InternalEdgeRole.JUNCTION
    )
    graph.edges["downstream"] = _edge("downstream", "hub", "dst")
    return graph


def test_hub_with_directly_attached_transport_edge_routes_pocket_forward() -> None:
    """Regression test: a pocket flowing INTO a hub via a JUNCTION edge must
    still find an outgoing TRANSPORT edge attached directly to that hub node
    (not just edges one further JUNCTION hop away) - this is the withdraw-
    through-a-valve's-common-port shape that was silently discarding mass."""
    graph = _valve_common_port_graph()
    pocket = _hot_pocket()
    state = TransportState(
        edge_queues={
            "upstream": deque([pocket]),
            "downstream": deque(),
        }
    )
    hyd_state = HydraulicState(
        pressures={},
        flows={
            "upstream": 1.0e-5,
            "port1.hub": 1.0e-5,
            "downstream": 1.0e-5,
        },
    )

    result = advance(graph, hyd_state, state, dt=0.1)

    assert result.arrivals == {}
    assert list(result.next_state.edge_queues["upstream"]) == []
    routed = list(result.next_state.edge_queues["downstream"])
    assert len(routed) == 1
    assert routed[0].volume == pytest.approx(pocket.volume)
    assert routed[0].species_moles == pytest.approx(pocket.species_moles)


def test_hub_with_directly_attached_transport_edge_routes_pocket_reverse() -> None:
    """The already-working direction (pocket originates on the hub-attached
    edge, exits through a neighboring port) must keep working after the fix."""
    graph = _valve_common_port_graph()
    pocket = _hot_pocket()
    state = TransportState(
        edge_queues={
            "upstream": deque(),
            "downstream": deque([pocket]),
        }
    )
    hyd_state = HydraulicState(
        pressures={},
        flows={
            "upstream": -1.0e-5,
            "port1.hub": -1.0e-5,
            "downstream": -1.0e-5,
        },
    )

    result = advance(graph, hyd_state, state, dt=0.1)

    assert result.arrivals == {}
    assert list(result.next_state.edge_queues["downstream"]) == []
    routed = list(result.next_state.edge_queues["upstream"])
    assert len(routed) == 1
    assert routed[0].volume == pytest.approx(pocket.volume)
    assert routed[0].species_moles == pytest.approx(pocket.species_moles)


def _valve_with_closed_port_graph() -> HydraulicGraph:
    """Mirror SixPortDistributionValve: `hub` has one OPEN junction port
    (draining normally to `dst`) and one CLOSED junction port (an
    unselected rotary-valve position, `resistance_override=R_MAX_HYDRAULIC`)
    whose downstream tube still solves a tiny nonzero residual flow - the
    finite-resistance numerical-stability trade-off documented on
    R_MAX_HYDRAULIC. That residual flow must not let hub content leak into
    it."""
    graph = HydraulicGraph()
    for node_id in ("src", "hub", "port_open", "dst", "port_closed", "leak_dst"):
        graph.nodes[node_id] = _node(node_id, is_hub=(node_id == "hub"))
    graph.edges["upstream"] = _edge("upstream", "src", "hub")
    graph.edges["hub.open"] = _edge(
        "hub.open", "hub", "port_open", role=InternalEdgeRole.JUNCTION
    )
    graph.edges["downstream"] = _edge("downstream", "port_open", "dst")
    graph.edges["hub.closed"] = _edge(
        "hub.closed",
        "hub",
        "port_closed",
        role=InternalEdgeRole.JUNCTION,
        resistance_override=R_MAX_HYDRAULIC,
    )
    graph.edges["leak_downstream"] = _edge("leak_downstream", "port_closed", "leak_dst")
    return graph


def test_closed_junction_port_excluded_from_hub_redistribution() -> None:
    """Regression test: a hub port whose JUNCTION edge is closed (an
    unselected rotary-valve position) must never receive hub-merged content,
    even though its finite (not infinite) resistance still solves a tiny
    nonzero residual flow on both the junction and its downstream tube -
    this was leaking a slow trickle of the active port's content into
    supposedly-isolated tubing."""
    graph = _valve_with_closed_port_graph()
    pocket = _hot_pocket()
    state = TransportState(
        edge_queues={
            "upstream": deque([pocket]),
            "downstream": deque(),
            "leak_downstream": deque(),
        }
    )
    hyd_state = HydraulicState(
        pressures={},
        flows={
            "upstream": 1.0e-5,
            "hub.open": 1.0e-5,
            "downstream": 1.0e-5,
            "hub.closed": 1.0e-11,  # tiny residual leak through R_MAX_HYDRAULIC
            "leak_downstream": 1.0e-11,
        },
    )

    result = advance(graph, hyd_state, state, dt=0.1)

    routed = list(result.next_state.edge_queues["downstream"])
    assert len(routed) == 1
    assert routed[0].species_moles == pytest.approx(pocket.species_moles)

    leaked = list(result.next_state.edge_queues["leak_downstream"])
    assert all("tracer" not in p.species_moles for p in leaked)


def test_dead_end_without_outgoing_transport_still_discards_pocket() -> None:
    graph = HydraulicGraph()
    graph.nodes["src"] = _node("src")
    graph.nodes["dead"] = _node("dead")
    graph.edges["upstream"] = _edge("upstream", "src", "dead")
    state = TransportState(edge_queues={"upstream": deque([_hot_pocket()])})
    hyd_state = HydraulicState(pressures={}, flows={"upstream": 1.0e-5})

    result = advance(graph, hyd_state, state, dt=0.1)

    assert result.arrivals == {}
    assert list(result.next_state.edge_queues["upstream"]) == []


def test_inject_pads_underfilled_transport_edge_with_air_carrier() -> None:
    graph = HydraulicGraph()
    graph.nodes["src"] = _node("src")
    graph.nodes["dst"] = _node("dst")
    graph.edges["edge"] = _edge("edge", "src", "dst")
    state = TransportState(edge_queues={"edge": deque()})
    hyd_state = HydraulicState(
        pressures={"src": 150_000.0},
        flows={"edge": 1.0e-6},
    )

    result = inject(state, {}, hyd_state, graph)

    queue = list(result.edge_queues["edge"])
    assert len(queue) == 1
    assert queue[0].phase_kind == PhaseKind.GAS
    assert queue[0].species_moles["air"] > 0.0
    assert queue[0].pressure == pytest.approx(150_000.0)
    expected_volume = math.pi * (graph.edges["edge"].diameter / 2.0) ** 2
    assert queue[0].volume == pytest.approx(expected_volume)


def test_inject_ignores_subtolerance_deficit_on_transport_edge() -> None:
    graph = HydraulicGraph()
    graph.nodes["src"] = _node("src")
    graph.nodes["dst"] = _node("dst")
    graph.edges["edge"] = _edge("edge", "src", "dst")
    edge = graph.edges["edge"]
    capacity = math.pi * (edge.diameter / 2.0) ** 2 * edge.length
    pocket = _hot_pocket(volume=capacity - 1.0e-13)
    state = TransportState(edge_queues={"edge": deque([pocket])})
    hyd_state = HydraulicState(
        pressures={"src": 150_000.0},
        flows={"edge": 1.0e-6},
    )

    result = inject(state, {}, hyd_state, graph)

    queue = list(result.edge_queues["edge"])
    assert len(queue) == 1
    assert queue[0] is pocket


def test_transport_heat_exchange_applies_stable_plug_flow_ua_model() -> None:
    pocket = Pocket(
        phase_kind=PhaseKind.GAS,
        volume=1.0e-6,
        species_moles={"air": 2.0e-5},
        temperature=300.0,
        pressure=101_325.0,
    )
    state = TransportState(edge_queues={"reactor.1.2": deque([pocket])})
    entry = TransportHeatExchangeEntry(
        edge_id="reactor.1.2",
        U=10.0,
        diameter=2.0e-3,
        T_wall=350.0,
    )

    apply_transport_heat_exchange(state, [entry], dt=0.5)

    c_thermal = (
        pocket.species_moles["air"]
        * COMPOUNDS["air"].cp("gas").to_base_units().magnitude
    )
    area = (4.0 / entry.diameter) * pocket.volume
    expected = entry.T_wall + (pocket.temperature - entry.T_wall) * math.exp(
        -(entry.U * area / c_thermal) * 0.5
    )
    heated = state.edge_queues["reactor.1.2"][0]
    assert heated.temperature == pytest.approx(expected)
    assert heated.volume == pytest.approx(pocket.volume)
    assert heated.pressure == pytest.approx(pocket.pressure)
    assert heated.species_moles == pocket.species_moles
