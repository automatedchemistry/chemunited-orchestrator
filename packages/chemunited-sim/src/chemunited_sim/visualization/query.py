"""Structured time-series queries over a recorded simulation database.

Unlike :func:`.pyvis_export.load_latest_snapshot` (single latest time point)
these functions return the full-run history for one identifier at a time, so
callers — in particular the MCP result tools — can inspect how a value
evolved rather than only its final state. Reuses the same DB-read queries
:mod:`.dashboard` already implements for the HTML dashboard, converted to the
same human-readable units (bar, mL/min, K).
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from .dashboard import (
    _PA_TO_BAR,
    _read_cell_temperatures,
    _read_edge_flows,
    _read_inventory_states,
    _read_node_pressures,
    _read_species_moles,
)
from .pyvis_export import NoSnapshotsError, SnapshotReadError, load_latest_snapshot

_M3S_TO_MLMIN = 6e7
_M3_TO_ML = 1e6


def _connect_ro(db_path: str | os.PathLike) -> sqlite3.Connection:
    path = Path(db_path)
    uri = f"file:{path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as exc:
        raise SnapshotReadError(f"Could not open simulation DB: {path}") from exc


def _tail(points: list, tail: int | None) -> list:
    return points[-tail:] if tail else points


def list_result_ids(db_path: str | os.PathLike) -> dict:
    """Return every node and edge identifier recorded in *db_path*.

    Use this before calling :func:`read_node_profile` or
    :func:`read_edge_profile` to discover valid ``node_id``/``edge_id``
    values — these are internal hydraulic-graph identifiers (e.g. a vessel's
    inventory node is ``"<component_name>.Inventory"``), not the component
    names used elsewhere in the API.
    """
    conn = _connect_ro(db_path)
    try:
        nodes = sorted(
            row["node_id"]
            for row in conn.execute("SELECT DISTINCT node_id FROM node_pressure")
        )
        edges = sorted(
            row["edge_id"]
            for row in conn.execute("SELECT DISTINCT edge_id FROM edge_flow")
        )
    except sqlite3.Error as exc:
        raise SnapshotReadError(
            f"Could not read simulation DB: {Path(db_path)}"
        ) from exc
    finally:
        conn.close()

    if not nodes and not edges:
        raise NoSnapshotsError(
            f"No recorded snapshots in simulation DB: {Path(db_path)}"
        )
    return {"nodes": nodes, "edges": edges}


def read_node_profile(
    db_path: str | os.PathLike, node_id: str, tail: int | None = None
) -> dict:
    """Return the full-run time series recorded for one node.

    Includes hydraulic pressure (bar), inventory temperature (K), and
    per-phase species content (moles) over the entire run. A node without
    tracked inventory (e.g. a plain junction) simply has an empty
    ``content``. Pass *tail* to keep only the last N recorded points.
    """
    conn = _connect_ro(db_path)
    try:
        pressures = _read_node_pressures(conn).get(node_id, [])
        inv_states = _read_inventory_states(conn).get(node_id, [])
        species = _read_species_moles(conn)
    except sqlite3.Error as exc:
        raise SnapshotReadError(
            f"Could not read simulation DB: {Path(db_path)}"
        ) from exc
    finally:
        conn.close()

    if not pressures and not inv_states:
        raise NoSnapshotsError(
            f"No recorded data for node '{node_id}' in {Path(db_path)}"
        )

    content: dict[str, dict[str, list]] = {}
    for key, species_series in species.items():
        key_node, _, phase = key.partition(" / ")
        if key_node != node_id:
            continue
        content[phase] = {
            sp: [{"time_s": t, "moles": m} for t, m in _tail(points, tail)]
            for sp, points in species_series.items()
        }

    return {
        "node_id": node_id,
        "pressure_bar": [{"time_s": t, "value": p} for t, p in _tail(pressures, tail)],
        "temperature_k": [
            {"time_s": t, "value": temp}
            for t, _pressure, temp in _tail(inv_states, tail)
        ],
        "content": content,
    }


def read_edge_profile(
    db_path: str | os.PathLike, edge_id: str, tail: int | None = None
) -> dict:
    """Return the full-run time series recorded for one transport edge.

    Includes flow rate (mL/min) and average cell temperature (K, where
    recorded) over the entire run. Pass *tail* to keep only the last N
    recorded points.
    """
    conn = _connect_ro(db_path)
    try:
        flows = _read_edge_flows(conn).get(edge_id, [])
        temps = _read_cell_temperatures(conn).get(edge_id, [])
    except sqlite3.Error as exc:
        raise SnapshotReadError(
            f"Could not read simulation DB: {Path(db_path)}"
        ) from exc
    finally:
        conn.close()

    if not flows:
        raise NoSnapshotsError(
            f"No recorded data for edge '{edge_id}' in {Path(db_path)}"
        )

    return {
        "edge_id": edge_id,
        "flow_mlmin": [{"time_s": t, "value": f} for t, f in _tail(flows, tail)],
        "temperature_k": [
            {"time_s": t, "value": temp} for t, temp in _tail(temps, tail)
        ],
    }


def read_latest_state(db_path: str | os.PathLike) -> dict:
    """Return a cross-sectional snapshot of every node and edge at the
    most recently recorded simulation time.

    Wraps :func:`.pyvis_export.load_latest_snapshot`, converting its raw SI
    values to the same human-readable units (bar, mL/min, mL) used by
    :func:`read_node_profile`/:func:`read_edge_profile`, so all three result
    tools agree on units.
    """
    snapshot = load_latest_snapshot(db_path)
    return {
        "time_s": snapshot.time,
        "pressures_bar": {
            node_id: p * _PA_TO_BAR for node_id, p in snapshot.pressures.items()
        },
        "flows_mlmin": {
            edge_id: f * _M3S_TO_MLMIN for edge_id, f in snapshot.flows.items()
        },
        "inventories": {
            node_id: {
                "pressure_bar": inv.pressure * _PA_TO_BAR,
                "temperature_k": inv.temperature,
                "phase_volumes_ml": {
                    phase: vol * _M3_TO_ML for phase, vol in inv.phase_volumes.items()
                },
                "species_moles": inv.species_moles,
            }
            for node_id, inv in snapshot.inventories.items()
        },
    }
