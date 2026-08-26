"""Inventory state seeding for chemunited-sim.

Reads the deep-copied ``InventoryNode`` snapshots from ``HydraulicGraph``
and builds one ``InventoryState`` per vessel.
"""

from __future__ import annotations

from ..adapter.models import HydraulicGraph
from ..common.constant import AMBIENT_TEMPERATURE_K, ATMOSPHERE_PRESSURE_PA
from .models import InventoryState


def build_inventory_states(graph: HydraulicGraph) -> dict[str, InventoryState]:
    """Seed one :class:`InventoryState` per vessel from the graph's inventory snapshots.

    Uses the deep-copied ``InventoryNode`` objects stored in
    ``HydraulicGraph.inventory_nodes``.  These snapshots are independent of
    the live component state — subsequent ``sync_internal_state()`` calls on
    the source component have no effect here.

    **Temperature seeding**: a single temperature is computed as the
    volume-weighted average of ``liq_content.initial_temperature`` and
    ``gas_content.initial_temperature``.  For the default all-gas vessel
    (``liq_content.volume == 0``), this reduces to the gas initial
    temperature.

    **Pressure seeding**: taken from whichever phase has non-zero initial
    volume, preferring gas.  The worker will overwrite this immediately with
    the first hydraulic solve result.

    Parameters
    ----------
    graph:
        The compiled hydraulic graph containing inventory snapshots.

    Returns
    -------
    dict[str, InventoryState]
        Keyed by ``inv_node_id`` (e.g. ``"vessel1.Inventory"``).
    """
    states: dict[str, InventoryState] = {}

    for inv_node_id, inv_node in graph.inventory_nodes.items():
        liq = inv_node.liq_content
        gas = inv_node.gas_content

        liq_vol = liq.volume
        gas_vol = gas.volume
        capacity = liq_vol + gas_vol

        # Single blended temperature (volume-weighted; instantaneous equilibrium)
        if capacity > 0.0:
            temperature = (
                liq_vol * liq.initial_temperature + gas_vol * gas.initial_temperature
            ) / capacity
        else:
            temperature = AMBIENT_TEMPERATURE_K

        # Pressure seed — solver will overwrite on the first step
        if gas_vol > 0.0:
            pressure = gas.initial_pressure
        elif liq_vol > 0.0:
            pressure = liq.initial_pressure
        else:
            pressure = ATMOSPHERE_PRESSURE_PA
        if pressure <= 0.0:
            pressure = ATMOSPHERE_PRESSURE_PA

        states[inv_node_id] = InventoryState(
            node_id=inv_node_id,
            capacity=capacity,
            pressure=pressure,
            temperature=temperature,
            liq_volume=liq_vol,
            gas_volume=gas_vol,
            liq_species_moles=dict(liq.initial_species),
            gas_species_moles=dict(gas.initial_species),
        )

    return states
