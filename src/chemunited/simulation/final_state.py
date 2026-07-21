"""Render a recorded simulation snapshot onto the live canvas.

Reads a chemunited-sim recording database and pushes vessel inventories and
tubing (edge) content onto the matching ``GraphComponent``/
``HydraulicConnectionItem`` instances, so the canvas reflects how the
platform looked at a given recorded instant. ``apply_final_simulation_state``
is a one-shot convenience for "the last recorded instant"; the underlying
``apply_simulation_state_at`` primitive and ``list_recorded_times`` are also
used by ``chemunited.simulation.playback.SimulationPlayback`` to scrub to any
recorded instant. ``load_edge_cells`` is likewise reused by
``chemunited.simulation.simulate_report.SimDbReader`` to build a
length-resolved content profile plot for the selected edge.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from pathlib import Path

from chemunited_core.common.enums import PhaseKind
from chemunited_core.components.plugflow import PlugFlowComponentData
from chemunited_core.compounds import VolumeContentBase
from chemunited_core.figure_registry import SolenoidValve2WayData, SolenoidValveData
from chemunited_core.figure_registry.rotary_valve import RotaryValveData
from loguru import logger

from chemunited.elements.access import Components, Connections
from chemunited.orchestrator.inventory_state import apply_inventory_status_payload

_CARRIER_SPECIES = "__carrier__"

# One cell's phase content: (phase_kind, phase_fraction, temperature, length_m, species->moles)
_CellPhase = tuple[PhaseKind, float, float, float, dict[str, float]]


def apply_final_simulation_state(
    components: Components, connections: Connections, db_path: Path
) -> None:
    """Read the last snapshot from *db_path* and render it on the canvas."""
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        logger.warning(f"Could not open simulation DB '{db_path}': {exc}")
        return

    try:
        t = _latest_time(conn)
        if t is None:
            return
        apply_simulation_state_at(conn, t, components, connections)
    except Exception:
        logger.opt(exception=True).warning(
            f"Failed to apply final simulation state from '{db_path}'"
        )
    finally:
        conn.close()


def apply_simulation_state_at(
    conn: sqlite3.Connection,
    t: float,
    components: Components,
    connections: Connections,
) -> None:
    """Render the recorded snapshot at exactly *t* onto the canvas.

    *conn* must already be open (row_factory ``sqlite3.Row``); the caller
    owns its lifecycle. Shared by ``apply_final_simulation_state`` above and
    ``SimulationPlayback``, which keeps one connection open across a
    time-scrubbing session instead of reopening it per frame.
    """
    _apply_inventories(conn, t, components)
    _apply_edge_content(conn, t, connections)
    _apply_internal_edge_content(conn, t, components)
    _apply_discrete_state(conn, t, components)


def _latest_time(conn: sqlite3.Connection) -> float | None:
    try:
        row = conn.execute("SELECT MAX(time) AS time FROM node_pressure").fetchone()
    except sqlite3.Error:
        return None
    if row is None or row["time"] is None:
        return None
    return float(row["time"])


def list_recorded_times(conn: sqlite3.Connection) -> list[float]:
    """Return every recorded snapshot instant in *conn*, sorted ascending.

    These are the only valid "frames" to scrub to — there is no
    interpolation between them.
    """
    try:
        rows = conn.execute(
            "SELECT DISTINCT time FROM node_pressure ORDER BY time"
        ).fetchall()
    except sqlite3.Error:
        return []
    return [float(row["time"]) for row in rows]


def _build_inventory_payload(
    conn: sqlite3.Connection, t: float
) -> dict[str, dict[str, dict[str, dict]]]:
    payload: dict[str, dict[str, dict[str, dict]]] = {}
    for row in conn.execute(
        "SELECT node_id, phase, species_id, moles, volume FROM inventory_content "
        "WHERE time = ?",
        (t,),
    ):
        component_name, _, inventory_key = str(row["node_id"]).partition(".")
        if not inventory_key:
            continue
        phase_payload = (
            payload.setdefault(component_name, {})
            .setdefault(inventory_key, {})
            .setdefault(str(row["phase"]), {"volume": 0.0, "initial_species": {}})
        )
        phase_payload["volume"] = float(row["volume"])
        species_id = str(row["species_id"])
        if species_id != _CARRIER_SPECIES:
            phase_payload["initial_species"][species_id] = float(row["moles"])
    return payload


def _apply_inventories(
    conn: sqlite3.Connection, t: float, components: Components
) -> None:
    payload = _build_inventory_payload(conn, t)
    if not payload:
        return

    apply_inventory_status_payload(components, payload)  # type: ignore[arg-type]
    for component_name in payload:
        component = components.get(component_name)
        if component is not None:
            component.graph.sync_visuals()


def _apply_discrete_state(
    conn: sqlite3.Connection, t: float, components: Components
) -> None:
    """Restore rotary valve rotor position / solenoid open-closed at *t*.

    These are the only component fields ``apply()`` mutates that aren't
    otherwise recoverable from continuous data, recorded into
    ``component_state`` as a JSON blob per component per snapshot. Missing
    table (an older recording) is treated as "nothing to restore."
    """
    try:
        rows = conn.execute(
            "SELECT component, state FROM component_state WHERE time = ?", (t,)
        ).fetchall()
    except sqlite3.Error:
        return

    for row in rows:
        component = components.get(str(row["component"]))
        if component is None:
            continue
        state = json.loads(row["state"])
        data = component.inf
        changed = False
        if "rotor_ports" in state and isinstance(data, RotaryValveData):
            data.rotor_ports = [tuple(port) for port in state["rotor_ports"]]
            changed = True
        elif "opened" in state and isinstance(
            data, (SolenoidValveData, SolenoidValve2WayData)
        ):
            data.opened = bool(state["opened"])
            changed = True
        if changed:
            data.sync_internal_state()
            component.graph.sync_visuals()


def _cells_to_content(
    cells: dict[int, list[_CellPhase]], cross_section_area: float
) -> list[VolumeContentBase]:
    content: list[VolumeContentBase] = []
    # cell_index 0 = origin end; EdgeData.content[0] must be destination-side,
    # so walk cells from the destination end (highest index) to the origin.
    for cell_index in sorted(cells, reverse=True):
        for phase_kind, phase_fraction, temperature, length_m, species in cells[
            cell_index
        ]:
            if phase_fraction <= 0:
                continue
            content.append(
                VolumeContentBase(
                    phase_kind=phase_kind,
                    volume=phase_fraction * length_m * cross_section_area,
                    initial_species=species,
                    initial_temperature=temperature,
                )
            )
    return content


def _apply_edge_content(
    conn: sqlite3.Connection, t: float, connections: Connections
) -> None:
    for edge_id, connection in connections.hydraulic.items():
        cells = load_edge_cells(conn, edge_id, t)
        if cells is None:
            continue  # unknown edge: no static cell geometry recorded for it

        cross_section_area = math.pi * (connection.inf.diameter_value / 2.0) ** 2
        connection.inf.content = _cells_to_content(cells, cross_section_area)
        connection.update()


def _apply_internal_edge_content(
    conn: sqlite3.Connection, t: float, components: Components
) -> None:
    """Render composite components' own internal transport tubing (Loop, FlowReactor).

    Their internal edge is compiled by chemunited-sim as ``f"{name}.{origin}.{dest}"``
    (``compile_plugflow``) and recorded into the same ``edge_cells``/``cell_state``/
    ``cell_content`` tables as external edges, but it never runs through a
    ``HydraulicConnectionItem`` — the content is written straight onto the
    component's own data so its graphics item can paint from it.
    """
    for name, component in components.items():
        data = component.inf
        if not isinstance(data, PlugFlowComponentData):
            continue

        cross_section_area = math.pi * (data.diameter_value / 2.0) ** 2
        for origin, destination in data.internal_edges:
            edge_id = f"{name}.{origin}.{destination}"
            cells = load_edge_cells(conn, edge_id, t)
            if cells is None:
                continue  # unknown edge: no static cell geometry recorded for it

            data.content = _cells_to_content(cells, cross_section_area)
            component.graph.sync_visuals()


def load_edge_cells(
    conn: sqlite3.Connection, edge_id: str, t: float
) -> dict[int, list[_CellPhase]] | None:
    """Return per-cell phase content for *edge_id* at *t*.

    Returns ``None`` if *edge_id* has no recorded static cell geometry (an
    unknown edge). Returns ``{}`` (a valid, non-None result) if the edge is
    known but had zero recorded content at exactly *t* — the recorder omits
    ``cell_state``/``cell_content`` rows entirely for an edge whose transport
    queue is empty at a given tick, so an empty tube is a real, distinct
    outcome from an unknown edge and callers must clear old content for it
    rather than skipping.
    """
    lengths: dict[int, float] = {
        int(row["cell_index"]): float(row["length_m"])
        for row in conn.execute(
            "SELECT cell_index, length_m FROM edge_cells WHERE edge_id = ?",
            (edge_id,),
        )
    }
    if not lengths:
        return None

    species_by_cell_phase: dict[tuple[int, str], dict[str, float]] = defaultdict(dict)
    for row in conn.execute(
        "SELECT cell_index, phase, species_id, moles FROM cell_content "
        "WHERE edge_id = ? AND time = ?",
        (edge_id, t),
    ):
        key = (int(row["cell_index"]), str(row["phase"]))
        species_by_cell_phase[key][str(row["species_id"])] = float(row["moles"])

    cells: dict[int, list[_CellPhase]] = defaultdict(list)
    for row in conn.execute(
        "SELECT cell_index, phase, phase_fraction, temperature FROM cell_state "
        "WHERE edge_id = ? AND time = ?",
        (edge_id, t),
    ):
        cell_index = int(row["cell_index"])
        phase = str(row["phase"])
        length_m = lengths.get(cell_index)
        if length_m is None:
            continue
        cells[cell_index].append(
            (
                PhaseKind(phase),
                float(row["phase_fraction"]),
                float(row["temperature"]),
                length_m,
                species_by_cell_phase.get((cell_index, phase), {}),
            )
        )
    return cells
