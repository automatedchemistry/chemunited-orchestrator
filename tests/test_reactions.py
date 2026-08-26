"""Tests for inventory and plug-flow reaction execution."""

from __future__ import annotations

from collections import deque

import pytest
from chemunited_core.common.enums import PhaseKind
from chemunited_core.figure_registry import COMPONENTS

from chemunited_sim.cli.builder import PlatformBuilder
from chemunited_sim.inventory.models import InventoryState
from chemunited_sim.reactions import FirstOrderDecay, apply, apply_transport
from chemunited_sim.transport.models import Pocket, TransportState


def _component(builder: PlatformBuilder, name: str, figure: str) -> None:
    builder.add_component(name=name, figure=figure)


def test_builder_resolves_vessel_and_flow_reactor_targets() -> None:
    builder = PlatformBuilder()
    _component(builder, "vessel", "GlassBottle")
    _component(builder, "reactor", "FlowReactor")
    _component(builder, "photo", "PhotoReactor")

    for target in ("vessel", "reactor", "photo"):
        builder.add_reaction(
            target,
            "FirstOrderDecay",
            reactant="a",
            product="b",
            rate_constant=0.1,
        )

    assert set(builder.reactions_map) == {
        "vessel.Inventory",
        "reactor.1.2",
        "photo.1.2",
    }


def test_builder_rejects_unknown_and_unsupported_targets() -> None:
    builder = PlatformBuilder()
    _component(builder, "pump", "HPLCPump")

    with pytest.raises(ValueError, match="Unknown reaction target"):
        builder.add_reaction(
            "missing",
            "FirstOrderDecay",
            reactant="a",
            product="b",
            rate_constant=0.1,
        )
    with pytest.raises(ValueError, match="does not support reactions"):
        builder.add_reaction(
            "pump",
            "FirstOrderDecay",
            reactant="a",
            product="b",
            rate_constant=0.1,
        )


def test_transport_reaction_updates_matching_pockets_and_preserves_geometry() -> None:
    liquid = Pocket(
        phase_kind=PhaseKind.LIQUID,
        volume=2.0e-6,
        species_moles={"a": 2.0, "spectator": 3.0},
        temperature=300.0,
        pressure=200_000.0,
    )
    gas = Pocket(
        phase_kind=PhaseKind.GAS,
        volume=1.0e-6,
        species_moles={"a": 1.0},
        temperature=310.0,
        pressure=150_000.0,
    )
    state = TransportState(edge_queues={"reactor.1.2": deque([liquid, gas])})
    reaction = FirstOrderDecay(
        reactant="a",
        product="b",
        rate_constant=0.25,
        phase=PhaseKind.LIQUID,
        delta_temperature_per_mol_converted=4.0,
    )

    apply_transport(state, {"reactor.1.2": [reaction]}, dt=2.0)

    reacted_liquid, untouched_gas = state.edge_queues["reactor.1.2"]
    assert reacted_liquid is not liquid
    assert reacted_liquid.volume == pytest.approx(2.0e-6)
    assert reacted_liquid.pressure == pytest.approx(200_000.0)
    assert reacted_liquid.species_moles == pytest.approx(
        {"a": 1.0, "b": 1.0, "spectator": 3.0}
    )
    assert reacted_liquid.temperature == pytest.approx(304.0)
    assert untouched_gas.species_moles == {"a": 1.0}
    assert untouched_gas.temperature == pytest.approx(310.0)


def test_transport_reactions_execute_sequentially() -> None:
    state = TransportState(
        edge_queues={
            "reactor.1.2": deque(
                [
                    Pocket(
                        phase_kind=PhaseKind.LIQUID,
                        volume=1.0,
                        species_moles={"a": 1.0},
                        temperature=298.0,
                        pressure=101_325.0,
                    )
                ]
            )
        }
    )
    reactions = [
        FirstOrderDecay("a", "b", 1.0, PhaseKind.LIQUID),
        FirstOrderDecay("b", "c", 1.0, PhaseKind.LIQUID),
    ]

    apply_transport(state, {"reactor.1.2": reactions}, dt=1.0)

    pocket = state.edge_queues["reactor.1.2"][0]
    assert pocket.species_moles == pytest.approx({"a": 0.0, "b": 0.0, "c": 1.0})


def test_inventory_reaction_behavior_remains_available() -> None:
    state = InventoryState(
        node_id="vessel.Inventory",
        capacity=1.0,
        pressure=101_325.0,
        temperature=298.0,
        liq_volume=1.0,
        gas_volume=0.0,
        liq_species_moles={"a": 1.0},
    )
    reaction = FirstOrderDecay("a", "b", 0.5, PhaseKind.LIQUID, 2.0)

    apply({"vessel.Inventory": state}, {"vessel.Inventory": [reaction]}, dt=1.0)

    assert state.liq_species_moles == pytest.approx({"a": 0.5, "b": 0.5})
    assert state.temperature == pytest.approx(299.0)


@pytest.mark.parametrize("figure", ["FlowReactor", "PhotoReactor"])
def test_reactor_figures_are_registered(figure: str) -> None:
    assert figure in COMPONENTS
