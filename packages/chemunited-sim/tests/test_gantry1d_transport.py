"""A 1D gantry carries liquid into the fraction tube it is over."""

from __future__ import annotations

import pytest

from chemunited_core.common.enums import ConnectionType, PhaseKind
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_core.figure_registry import COMPONENTS
from chemunited_quantities import ChemUnitQuantity
from chemunited_sim.adapter import compile_graph, resync_component
from chemunited_sim.worker import SimConfig, Worker


def _make(figure: str, name: str, **kwargs):
    definition = COMPONENTS[figure]
    return definition.data_class.from_mode(definition.mode_class(name=name, **kwargs))


def test_gantry1d_contact_compiles_as_a_hydraulic_junction() -> None:
    gantry = _make("Gantry1D", "gantry", position_x="1", connections_number=3)
    tray = _make("Vial", "tray", column=3, row=1, pressure_access=False)
    contact = EdgeData.from_mode(
        EdgeMode(
            name="gantry_2_tray_1",
            origin="gantry",
            origin_port=2,
            destination="tray",
            destination_port=1,
            classification=ConnectionType.MOVEMENT,
        )
    )

    graph = compile_graph([gantry, tray], [contact])

    assert "gantry.2" in graph.nodes
    assert graph.edges["gantry_2_tray_1"].role.name == "JUNCTION"
    assert graph.edges["gantry.1.2"].resistance_override is None
    assert graph.edges["gantry.1.3"].resistance_override is not None


def _liquid_to_tray():
    """A pressurised bottle, a tube, a 1D gantry and a tray of three open tubes."""
    source = _make("Source", "argon", setpoint=ChemUnitQuantity("1.2 bar"))
    bottle = _make(
        "GlassBottle",
        "bottle",
        capacity=ChemUnitQuantity("100 ml"),
        top_access=1,
        bottom_access=1,
        pressure_access=True,
    )
    bottle.internal_inventory.liq_content.volume = 80.0e-6
    bottle.internal_inventory.liq_content.initial_species = {"water": 4.0}
    bottle.internal_inventory.gas_content.volume = 20.0e-6
    bottle.internal_inventory.gas_content.initial_species = {"air": 8.0e-4}
    gantry = _make("Gantry1D", "gantry", position_x="2", connections_number=3)
    tray = _make(
        "Vial",
        "tray",
        column=3,
        row=1,
        pressure_access=False,
        capacity=ChemUnitQuantity("50 ml"),
    )
    edges = [
        EdgeData.from_mode(
            EdgeMode(
                name="argon_1_bottle_1",
                origin="argon",
                origin_port=1,
                destination="bottle",
                destination_port=1,
                classification=ConnectionType.HYDRAULIC,
                length="100 mm",
                diameter="1 mm",
            )
        ),
        EdgeData.from_mode(
            EdgeMode(
                name="bottle_2_gantry_1",
                origin="bottle",
                origin_port=2,
                destination="gantry",
                destination_port=1,
                classification=ConnectionType.HYDRAULIC,
                length="100 mm",
                diameter="1 mm",
            )
        ),
    ]
    for position in range(1, 4):
        edges.append(
            EdgeData.from_mode(
                EdgeMode(
                    name=f"gantry_{position + 1}_tray_{position}",
                    origin="gantry",
                    origin_port=position + 1,
                    destination="tray",
                    destination_port=position,
                    classification=ConnectionType.MOVEMENT,
                )
            )
        )
    return [source, bottle, gantry, tray], edges


def test_liquid_reaches_only_the_tube_the_gantry_is_over() -> None:
    components, edges = _liquid_to_tray()
    graph = compile_graph(components, edges)
    worker = Worker(graph, components, SimConfig(dt=0.1))

    for _ in range(40):
        worker.step()

    assert worker.inv_states["tray.A2"].liq_volume > 1.0e-7
    assert worker.inv_states["tray.A1"].liq_volume == 0.0
    assert worker.inv_states["tray.A3"].liq_volume == 0.0


def test_a_vented_vessel_keeps_what_flows_into_it() -> None:
    components, edges = _liquid_to_tray()
    graph = compile_graph(components, edges)
    worker = Worker(graph, components, SimConfig(dt=0.1))
    start = worker.inv_states["bottle.Inventory"].liq_volume

    for _ in range(40):
        worker.step()

    left = worker.inv_states["bottle.Inventory"].liq_volume
    in_tube = sum(
        pocket.volume
        for pocket in worker.transport_state.edge_queues["bottle_2_gantry_1"]
        if pocket.phase_kind == PhaseKind.LIQUID
    )
    tubes = sum(
        worker.inv_states[f"tray.A{position}"].liq_volume for position in (1, 2, 3)
    )
    assert left + in_tube + tubes == pytest.approx(start, rel=1e-9)
    assert worker.inv_states["tray.A2"].liq_species_moles["water"] > 0.0


def test_homing_stops_liquid_reaching_any_tube() -> None:
    components, edges = _liquid_to_tray()
    gantry = components[2]
    graph = compile_graph(components, edges)
    worker = Worker(graph, components, SimConfig(dt=0.1))
    for _ in range(40):
        worker.step()
    before = worker.inv_states["tray.A2"].liq_volume

    gantry.apply("home", wait=True)
    resync_component(graph, gantry)
    for _ in range(20):
        worker.step()

    assert worker.inv_states["tray.A2"].liq_volume == pytest.approx(before)
    assert worker.inv_states["tray.A1"].liq_volume == 0.0
    assert worker.inv_states["tray.A3"].liq_volume == 0.0
