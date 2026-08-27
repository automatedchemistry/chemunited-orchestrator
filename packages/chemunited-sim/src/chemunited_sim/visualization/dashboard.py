"""HTML dashboard generator for chemunited-sim recorded data."""

from __future__ import annotations

import html
import json
import os
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, TypedDict

from ..adapter.models import HydraulicGraph
from .pyvis_export import NoSnapshotsError, SnapshotReadError

_PLOTLY_CDN = "https://cdn.plot.ly/plotly-2.35.2.min.js"

_PA_TO_BAR = 1e-5
_M3S_TO_MLMIN = 6e7
_FLAT_ABS_TOL = 1e-12
_FLAT_REL_TOL = 1e-6


@dataclass(frozen=True)
class TraceSpec:
    """Serializable chart trace with scanability metadata."""

    name: str
    x: list[float]
    y: list[float]
    minimum: float | None
    maximum: float | None
    value_range: float
    max_abs: float
    flat: bool
    default_visible: bool

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "min": self.minimum,
            "max": self.maximum,
            "range": self.value_range,
            "maxAbs": self.max_abs,
            "flat": self.flat,
            "defaultVisible": self.default_visible,
            "points": len(self.x),
        }


class _RawTrace(TypedDict):
    name: str
    x: list[float]
    y: list[float]
    minimum: float | None
    maximum: float | None
    range: float
    max_abs: float
    flat: bool


@dataclass(frozen=True)
class ChartSpec:
    """Serializable chart definition consumed by the client-side controller."""

    chart_id: str
    tab: str
    title: str
    x_label: str
    y_label: str
    traces: list[TraceSpec]

    @property
    def all_flat(self) -> bool:
        return bool(self.traces) and all(trace.flat for trace in self.traces)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.chart_id,
            "tab": self.tab,
            "title": self.title,
            "xLabel": self.x_label,
            "yLabel": self.y_label,
            "allFlat": self.all_flat,
            "traces": [trace.to_payload() for trace in self.traces],
        }


def render_dashboard_html(
    db_path: str | os.PathLike,
    graph: HydraulicGraph | None = None,
    components: Iterable[Any] | None = None,
) -> str:
    """Read all recorded time series from *db_path* and return dashboard HTML."""
    path = Path(db_path)
    uri = f"file:{path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        raise SnapshotReadError(f"Could not open simulation DB: {path}") from exc

    try:
        meta = _read_meta(conn)
        node_pressures = _read_node_pressures(conn)
        edge_flows = _read_edge_flows(conn)
        inv_states = _read_inventory_states(conn)
        species_moles = _read_species_moles(conn)
        cell_temps = _read_cell_temperatures(conn)
        cell_profiles = _read_cell_profiles(conn)
    except NoSnapshotsError:
        raise
    except sqlite3.Error as exc:
        raise SnapshotReadError(f"Could not read simulation DB: {path}") from exc
    finally:
        conn.close()

    return _build_html(
        path.stem,
        meta,
        node_pressures,
        edge_flows,
        inv_states,
        species_moles,
        cell_temps,
        cell_profiles,
        graph=graph,
        components=components,
    )


# ---------------------------------------------------------------------------
# DB readers
# ---------------------------------------------------------------------------


def _read_meta(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM meta")
    }


def _read_node_pressures(conn: sqlite3.Connection) -> dict[str, list]:
    """Returns {node_id: [(time, pressure_bar), ...]}."""
    series: dict[str, list] = defaultdict(list)
    for row in conn.execute(
        "SELECT time, node_id, pressure FROM node_pressure ORDER BY time"
    ):
        series[row["node_id"]].append(
            (float(row["time"]), float(row["pressure"]) * _PA_TO_BAR)
        )
    return dict(series)


def _read_edge_flows(conn: sqlite3.Connection) -> dict[str, list]:
    """Returns {edge_id: [(time, flow_nls), ...]}."""
    series: dict[str, list] = defaultdict(list)
    for row in conn.execute(
        "SELECT time, edge_id, flow_rate FROM edge_flow ORDER BY time"
    ):
        series[row["edge_id"]].append(
            (float(row["time"]), float(row["flow_rate"]) * _M3S_TO_MLMIN)
        )
    return dict(series)


def _read_inventory_states(conn: sqlite3.Connection) -> dict[str, list]:
    """Returns {node_id: [(time, pressure_bar, temperature_K), ...]}."""
    series: dict[str, list] = defaultdict(list)
    if not _table_exists(conn, "inventory_state"):
        return {}
    for row in conn.execute(
        "SELECT time, node_id, pressure, temperature FROM inventory_state ORDER BY time"
    ):
        series[row["node_id"]].append(
            (
                float(row["time"]),
                float(row["pressure"]) * _PA_TO_BAR,
                float(row["temperature"]),
            )
        )
    return dict(series)


def _read_species_moles(conn: sqlite3.Connection) -> dict[str, dict[str, list]]:
    """Returns {'node_id / phase': {species_id: [(time, moles), ...]}}."""
    series: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    if not _table_exists(conn, "inventory_content"):
        return {}
    for row in conn.execute("""
        SELECT time, node_id, phase, species_id, moles
        FROM inventory_content
        WHERE species_id != '__carrier__'
        ORDER BY time
        """):
        key = f"{row['node_id']} / {row['phase']}"
        series[key][row["species_id"]].append((float(row["time"]), float(row["moles"])))
    return {k: dict(v) for k, v in series.items()}


def _read_cell_temperatures(conn: sqlite3.Connection) -> dict[str, list]:
    """Returns {edge_id: [(time, avg_temp_K), ...]}."""
    series: dict[str, list] = defaultdict(list)
    if not _table_exists(conn, "cell_state"):
        return {}
    for row in conn.execute("""
        SELECT time, edge_id, AVG(temperature) AS avg_temp
        FROM cell_state
        GROUP BY time, edge_id
        ORDER BY time
        """):
        if row["avg_temp"] is not None:
            series[row["edge_id"]].append((float(row["time"]), float(row["avg_temp"])))
    return dict(series)


def _read_cell_profiles(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return spatial pipe-cell profiles grouped by edge and snapshot time."""
    has_state = _table_exists(conn, "cell_state")
    has_content = _table_exists(conn, "cell_content")
    if not has_state and not has_content:
        return {"times": [], "edges": []}

    geometry = _read_cell_geometry(conn)
    cell_indices: dict[str, set[int]] = defaultdict(set)
    phases: dict[str, set[str]] = defaultdict(set)
    species: dict[str, set[tuple[str, str]]] = defaultdict(set)
    edge_times: dict[str, set[str]] = defaultdict(set)
    times_by_key: dict[str, float] = {}
    state_values: dict[tuple[str, str, str, int], tuple[float, float]] = {}
    content_values: dict[tuple[str, str, str, str, int], float] = {}

    if has_state:
        for row in conn.execute("""
            SELECT time, edge_id, cell_index, phase, phase_fraction, temperature
            FROM cell_state
            ORDER BY time, edge_id, cell_index, phase
            """):
            time_value = _round_time(float(row["time"]))
            time_key = _time_key(time_value)
            edge_id = str(row["edge_id"])
            phase = str(row["phase"])
            cell_index = int(row["cell_index"])
            times_by_key[time_key] = time_value
            edge_times[edge_id].add(time_key)
            cell_indices[edge_id].add(cell_index)
            phases[edge_id].add(phase)
            state_values[(edge_id, time_key, phase, cell_index)] = (
                float(row["phase_fraction"]),
                float(row["temperature"]),
            )

    if has_content:
        for row in conn.execute("""
            SELECT time, edge_id, cell_index, phase, species_id, moles
            FROM cell_content
            ORDER BY time, edge_id, cell_index, phase, species_id
            """):
            time_value = _round_time(float(row["time"]))
            time_key = _time_key(time_value)
            edge_id = str(row["edge_id"])
            phase = str(row["phase"])
            species_id = str(row["species_id"])
            cell_index = int(row["cell_index"])
            times_by_key[time_key] = time_value
            edge_times[edge_id].add(time_key)
            cell_indices[edge_id].add(cell_index)
            phases[edge_id].add(phase)
            species[edge_id].add((phase, species_id))
            content_values[(edge_id, time_key, phase, species_id, cell_index)] = float(
                row["moles"]
            )

    time_payload = [
        {"key": key, "value": value, "label": f"{_format_number(value)} s"}
        for key, value in sorted(times_by_key.items(), key=lambda item: item[1])
    ]
    ordered_time_keys = [str(item["key"]) for item in time_payload]
    dynamic_edges = set(cell_indices) | set(edge_times)
    edges = []

    for edge_id in sorted(dynamic_edges):
        cells = geometry.get(edge_id)
        if not cells:
            cells = [
                {
                    "index": index,
                    "position": float(index),
                    "center": float(index),
                    "length": 1.0,
                }
                for index in sorted(cell_indices[edge_id])
            ]
        cell_order = [int(cell["index"]) for cell in cells]
        edge_phases = sorted(phases[edge_id])
        edge_species = [
            {
                "key": _content_trace_key(phase, species_id),
                "phase": phase,
                "speciesId": species_id,
                "name": f"{phase} / {species_id}",
            }
            for phase, species_id in sorted(species[edge_id])
        ]
        snapshots: dict[str, dict[str, Any]] = {}
        for time_key in ordered_time_keys:
            if time_key not in edge_times[edge_id]:
                continue
            phase_fractions: dict[str, list[float]] = {}
            temperatures: dict[str, list[float | None]] = {}
            for phase in edge_phases:
                phase_fractions[phase] = []
                temperatures[phase] = []
                for cell_index in cell_order:
                    values = state_values.get((edge_id, time_key, phase, cell_index))
                    if values is None:
                        phase_fractions[phase].append(0.0)
                        temperatures[phase].append(None)
                    else:
                        phase_fraction, temperature = values
                        phase_fractions[phase].append(phase_fraction)
                        temperatures[phase].append(temperature)

            contents: dict[str, list[float]] = {}
            for item in edge_species:
                phase = item["phase"]
                species_id = item["speciesId"]
                contents[item["key"]] = [
                    content_values.get(
                        (edge_id, time_key, phase, species_id, cell_index),
                        0.0,
                    )
                    for cell_index in cell_order
                ]

            snapshots[time_key] = {
                "phaseFractions": phase_fractions,
                "temperatures": temperatures,
                "contents": contents,
            }

        edges.append(
            {
                "edgeId": edge_id,
                "cellCount": len(cells),
                "xLabel": (
                    "Cell position (m)" if edge_id in geometry else "Cell index"
                ),
                "cells": cells,
                "phases": edge_phases,
                "species": edge_species,
                "snapshots": snapshots,
            }
        )

    return {"times": time_payload, "edges": edges}


def _read_cell_geometry(conn: sqlite3.Connection) -> dict[str, list[dict[str, float]]]:
    """Return cell geometry payloads keyed by edge id."""
    if not _table_exists(conn, "edge_cells"):
        return {}
    geometry: dict[str, list[dict[str, float]]] = defaultdict(list)
    for row in conn.execute("""
        SELECT edge_id, cell_index, position_m, length_m
        FROM edge_cells
        ORDER BY edge_id, cell_index
        """):
        position = float(row["position_m"])
        length = float(row["length_m"])
        geometry[str(row["edge_id"])].append(
            {
                "index": int(row["cell_index"]),
                "position": position,
                "center": position + 0.5 * length,
                "length": length,
            }
        )
    return dict(geometry)


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Element grouping
# ---------------------------------------------------------------------------


def _build_element_payload(
    *,
    node_pressures: dict[str, list],
    edge_flows: dict[str, list],
    inv_states: dict[str, list],
    species_moles: dict[str, dict[str, list]],
    cell_temps: dict[str, list],
    cell_profiles: dict[str, Any],
    graph: HydraulicGraph | None,
    components: Iterable[Any] | None,
) -> dict[str, list[dict[str, Any]]]:
    component_types = {
        str(comp.name): type(comp).__name__
        for comp in (components or [])
        if hasattr(comp, "name")
    }
    nodes_by_component: dict[str, set[str]] = defaultdict(set)
    inventory_by_component: dict[str, set[str]] = defaultdict(set)
    edges_by_component: dict[str, set[str]] = defaultdict(set)

    if graph is not None:
        for node_id, node in graph.nodes.items():
            comp = node.component or _component_from_node_id(node_id)
            if comp:
                nodes_by_component[comp].add(node_id)
        for inv_id in graph.inventory_nodes:
            comp = _component_from_node_id(inv_id)
            if comp:
                inventory_by_component[comp].add(inv_id)
                nodes_by_component[comp].add(inv_id)
        for edge_id, edge in graph.edges.items():
            comps = {
                graph.nodes[node_id].component
                for node_id in (edge.origin_node_id, edge.destination_node_id)
                if node_id in graph.nodes and graph.nodes[node_id].component
            }
            if edge.component:
                comps.add(edge.component)
            for comp in comps:
                edges_by_component[str(comp)].add(edge_id)
    else:
        for node_id in set(node_pressures) | set(inv_states):
            comp = _component_from_node_id(node_id)
            if comp:
                nodes_by_component[comp].add(node_id)
            if node_id.endswith(".Inventory") and comp:
                inventory_by_component[comp].add(node_id)
        for edge_id in set(edge_flows) | set(cell_temps):
            for comp in _components_from_edge_id(edge_id):
                edges_by_component[comp].add(edge_id)

    component_ids = (
        set(component_types)
        | set(nodes_by_component)
        | set(inventory_by_component)
        | set(edges_by_component)
    )
    components_payload = [
        _component_payload(
            component_id=component_id,
            component_type=component_types.get(component_id, "component"),
            node_ids=sorted(nodes_by_component.get(component_id, set())),
            inventory_ids=sorted(inventory_by_component.get(component_id, set())),
            edge_ids=sorted(edges_by_component.get(component_id, set())),
            node_pressures=node_pressures,
            edge_flows=edge_flows,
            inv_states=inv_states,
            species_moles=species_moles,
            cell_temps=cell_temps,
        )
        for component_id in sorted(component_ids)
    ]

    profile_by_edge = {edge["edgeId"]: edge for edge in cell_profiles.get("edges", [])}
    cell_times = cell_profiles.get("times", [])
    edge_ids = set(edge_flows) | set(cell_temps) | set(profile_by_edge)
    if graph is not None:
        edge_ids.update(graph.edges)
    edges_payload = [
        _edge_payload(
            edge_id=edge_id,
            graph=graph,
            node_pressures=node_pressures,
            edge_flows=edge_flows,
            cell_temps=cell_temps,
            cell_profile=profile_by_edge.get(edge_id),
            cell_times=cell_times,
        )
        for edge_id in sorted(edge_ids)
    ]
    return {"components": components_payload, "edges": edges_payload}


def _component_payload(
    *,
    component_id: str,
    component_type: str,
    node_ids: list[str],
    inventory_ids: list[str],
    edge_ids: list[str],
    node_pressures: dict[str, list],
    edge_flows: dict[str, list],
    inv_states: dict[str, list],
    species_moles: dict[str, dict[str, list]],
    cell_temps: dict[str, list],
) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    pressure_traces = [
        _trace_payload(node_id, [(t, p) for t, p in node_pressures[node_id]])
        for node_id in node_ids
        if node_id in node_pressures
    ]
    if pressure_traces:
        groups.append(
            _signal_group("Node pressures", "Pressure (bar)", pressure_traces)
        )

    inv_pressure_traces = [
        _trace_payload(inv_id, [(t, p) for t, p, _ in inv_states[inv_id]])
        for inv_id in inventory_ids
        if inv_id in inv_states
    ]
    if inv_pressure_traces:
        groups.append(
            _signal_group("Inventory pressures", "Pressure (bar)", inv_pressure_traces)
        )

    inv_temperature_traces = [
        _trace_payload(inv_id, [(t, temp) for t, _, temp in inv_states[inv_id]])
        for inv_id in inventory_ids
        if inv_id in inv_states
    ]
    if inv_temperature_traces:
        groups.append(
            _signal_group(
                "Inventory temperatures", "Temperature (K)", inv_temperature_traces
            )
        )

    species_traces = []
    for inv_id in inventory_ids:
        prefix = f"{inv_id} / "
        for group_key, species_dict in sorted(species_moles.items()):
            if not group_key.startswith(prefix):
                continue
            phase = group_key.removeprefix(prefix)
            for species_id, points in sorted(species_dict.items()):
                species_traces.append(_trace_payload(f"{phase} / {species_id}", points))
    if species_traces:
        groups.append(_signal_group("Inventory species", "Moles (mol)", species_traces))

    flow_traces = [
        _trace_payload(edge_id, edge_flows[edge_id])
        for edge_id in edge_ids
        if edge_id in edge_flows
    ]
    if flow_traces:
        groups.append(_signal_group("Related edge flows", "Flow (mL/min)", flow_traces))

    temp_traces = [
        _trace_payload(edge_id, cell_temps[edge_id])
        for edge_id in edge_ids
        if edge_id in cell_temps
    ]
    if temp_traces:
        groups.append(
            _signal_group("Related edge temperatures", "Temperature (K)", temp_traces)
        )

    return {
        "id": component_id,
        "type": component_type,
        "nodes": node_ids,
        "inventories": inventory_ids,
        "edges": edge_ids,
        "signals": groups,
    }


def _edge_payload(
    *,
    edge_id: str,
    graph: HydraulicGraph | None,
    node_pressures: dict[str, list],
    edge_flows: dict[str, list],
    cell_temps: dict[str, list],
    cell_profile: dict[str, Any] | None,
    cell_times: list[dict[str, Any]],
) -> dict[str, Any]:
    edge = graph.edges.get(edge_id) if graph is not None else None
    origin = edge.origin_node_id if edge is not None else None
    destination = edge.destination_node_id if edge is not None else None
    groups = []
    if edge_id in edge_flows:
        groups.append(
            _signal_group(
                "Flow rate",
                "Flow (mL/min)",
                [_trace_payload(edge_id, edge_flows[edge_id])],
            )
        )
    if edge_id in cell_temps:
        groups.append(
            _signal_group(
                "Average cell temperature",
                "Temperature (K)",
                [_trace_payload(edge_id, cell_temps[edge_id])],
            )
        )
    content_traces = _cell_content_time_traces(cell_profile, cell_times)
    if content_traces:
        groups.append(
            _signal_group(
                "Average cell content",
                "Mean moles per cell (mol)",
                content_traces,
            )
        )
    endpoint_traces = [
        _trace_payload(node_id, node_pressures[node_id])
        for node_id in (origin, destination)
        if node_id is not None and node_id in node_pressures
    ]
    if endpoint_traces:
        groups.append(
            _signal_group("Endpoint pressures", "Pressure (bar)", endpoint_traces)
        )

    return {
        "id": edge_id,
        "role": edge.role.name if edge is not None else "recorded",
        "origin": origin,
        "destination": destination,
        "component": edge.component if edge is not None else None,
        "external": bool(edge.is_external) if edge is not None else None,
        "length": edge.length if edge is not None else None,
        "diameter": edge.diameter if edge is not None else None,
        "signals": groups,
        "cellProfile": cell_profile,
    }


def _cell_content_time_traces(
    cell_profile: dict[str, Any] | None,
    cell_times: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not cell_profile:
        return []
    species = cell_profile.get("species", [])
    snapshots = cell_profile.get("snapshots", {})
    if not species or not snapshots:
        return []

    traces = []
    cell_count = int(cell_profile.get("cellCount") or 0)
    for item in species:
        points = []
        trace_key = item["key"]
        for time_item in cell_times:
            time_key = str(time_item["key"])
            snapshot = snapshots.get(time_key)
            if snapshot is None:
                continue
            values = snapshot.get("contents", {}).get(trace_key)
            if values is None:
                values = [0.0] * cell_count
            if not values:
                continue
            mean_moles = sum(float(value or 0.0) for value in values) / len(values)
            points.append((float(time_item["value"]), mean_moles))
        if points:
            traces.append(_trace_payload(str(item["name"]), points))
    return traces


def _signal_group(
    title: str,
    y_label: str,
    traces: list[dict[str, Any]],
) -> dict[str, Any]:
    return {"title": title, "yLabel": y_label, "traces": traces}


def _trace_payload(name: str, points: list) -> dict[str, Any]:
    values = [float(point[1]) for point in points]
    return {
        "name": name,
        "x": [_round_time(float(point[0])) for point in points],
        "y": values,
        "points": len(values),
        "flat": _is_flat(values),
    }


def _is_flat(values: list[float]) -> bool:
    if not values:
        return True
    value_range = max(values) - min(values)
    max_abs = max(abs(value) for value in values)
    return value_range <= max(_FLAT_ABS_TOL, _FLAT_REL_TOL * max_abs)


def _component_from_node_id(node_id: str) -> str | None:
    if "." in node_id:
        return node_id.split(".", 1)[0]
    return node_id or None


def _components_from_edge_id(edge_id: str) -> set[str]:
    parts = [part for part in edge_id.split("_") if part]
    if len(parts) >= 3:
        return {parts[0], parts[2]}
    if "." in edge_id:
        return {edge_id.split(".", 1)[0]}
    return {edge_id} if edge_id else set()


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------


def _build_html(
    stem: str,
    meta: dict[str, str],
    node_pressures: dict[str, list],
    edge_flows: dict[str, list],
    inv_states: dict[str, list],
    species_moles: dict[str, dict[str, list]],
    cell_temps: dict[str, list],
    cell_profiles: dict[str, Any],
    *,
    graph: HydraulicGraph | None = None,
    components: Iterable[Any] | None = None,
) -> str:
    charts = _build_charts(
        node_pressures=node_pressures,
        edge_flows=edge_flows,
        inv_states=inv_states,
        species_moles=species_moles,
        cell_temps=cell_temps,
    )
    element_payload = _build_element_payload(
        node_pressures=node_pressures,
        edge_flows=edge_flows,
        inv_states=inv_states,
        species_moles=species_moles,
        cell_temps=cell_temps,
        cell_profiles=cell_profiles,
        graph=graph,
        components=components,
    )
    summary = _build_summary(
        node_pressures=node_pressures,
        edge_flows=edge_flows,
        inv_states=inv_states,
        species_moles=species_moles,
        cell_temps=cell_temps,
        cell_profiles=cell_profiles,
    )
    payload = {
        "stem": stem,
        "summary": summary,
        "tabs": [
            "pressures",
            "flows",
            "inventories",
            "species",
            "temperatures",
            "cells",
        ],
        "charts": [chart.to_payload() for chart in charts],
        "cellProfiles": cell_profiles,
        "components": element_payload["components"],
        "edges": element_payload["edges"],
        "emptyStates": {
            "components": "No component-level data were recorded.",
            "edges": "No edge-level data were recorded.",
            "pressures": "No node pressure traces were recorded.",
            "flows": "No edge flow traces were recorded.",
            "inventories": "No inventory state traces were recorded.",
            "species": "No tracked inventory species were recorded.",
            "temperatures": (
                "No inventory or edge cell temperature traces were recorded."
            ),
            "cells": "No pipe-cell state or content rows were recorded.",
        },
    }

    safe_stem = html.escape(stem)
    meta_rows = _render_meta_rows(meta)
    metric_cards = _render_metric_cards(summary["metrics"])
    payload_json = _json_script_payload(payload)
    t_min = summary["timeStart"]
    t_max = summary["timeEnd"]

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dashboard - {safe_stem}</title>
<script src="{_PLOTLY_CDN}"></script>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
      "Segoe UI", sans-serif;
    background: #f6f7f9;
    color: #20242c;
  }}
  header {{
    background: #ffffff;
    border-bottom: 1px solid #dde3ea;
    padding: 20px 28px;
  }}
  .header-inner {{
    max-width: 1480px;
    margin: 0 auto;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 24px;
  }}
  .kicker {{
    color: #526070;
    font-size: 0.78rem;
    font-weight: 700;
    letter-spacing: 0;
    text-transform: uppercase;
  }}
  h1 {{
    margin: 4px 0 0;
    font-size: 1.7rem;
    line-height: 1.15;
    font-weight: 700;
  }}
  .time-range {{
    color: #526070;
    font-size: 0.92rem;
    white-space: nowrap;
  }}
  main {{
    max-width: 1480px;
    margin: 0 auto;
    padding: 22px 24px 36px;
  }}
  .metrics {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 12px;
    margin-bottom: 18px;
  }}
  .metric-card, .panel, .chart-card {{
    background: #ffffff;
    border: 1px solid #dde3ea;
    border-radius: 8px;
    box-shadow: 0 1px 2px rgba(20, 25, 35, 0.04);
  }}
  .metric-card {{ padding: 12px 14px; min-height: 72px; }}
  .metric-label {{
    color: #657181;
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0;
    text-transform: uppercase;
  }}
  .metric-value {{ margin-top: 6px; font-size: 1.12rem; font-weight: 700; }}
  .metric-unit {{ color: #657181; font-size: 0.82rem; font-weight: 500; }}
  .tabs {{
    display: flex;
    gap: 6px;
    border-bottom: 1px solid #d6dde6;
    margin: 8px 0 18px;
    overflow-x: auto;
  }}
  .tab-button {{
    appearance: none;
    border: 0;
    border-bottom: 3px solid transparent;
    background: transparent;
    color: #526070;
    cursor: pointer;
    font: inherit;
    font-size: 0.92rem;
    font-weight: 700;
    padding: 12px 14px 10px;
    white-space: nowrap;
  }}
  .tab-button.active {{ color: #0b5cad; border-bottom-color: #0b5cad; }}
  .tab-panel {{ display: none; }}
  .tab-panel.active {{ display: block; }}
  .panel {{ padding: 18px; margin-bottom: 16px; }}
  .panel h2, .chart-card h2 {{
    margin: 0;
    font-size: 1rem;
    line-height: 1.25;
  }}
  .panel-subtitle, .chart-meta {{
    margin-top: 5px;
    color: #657181;
    font-size: 0.84rem;
  }}
  .overview-grid {{
    display: grid;
    grid-template-columns: minmax(260px, 0.9fr) minmax(280px, 1.1fr);
    gap: 16px;
  }}
  table {{ border-collapse: collapse; width: 100%; font-size: 0.86rem; }}
  td {{ border-bottom: 1px solid #edf0f3; padding: 7px 8px; vertical-align: top; }}
  td:first-child {{ color: #526070; font-weight: 700; width: 170px; }}
  .toolbar {{
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 14px;
  }}
  .search-input, .select-input {{
    min-width: 260px;
    flex: 1;
    border: 1px solid #cbd4df;
    border-radius: 6px;
    color: #20242c;
    font: inherit;
    font-size: 0.9rem;
    padding: 9px 11px;
  }}
  .select-input {{ flex: 0 1 220px; }}
  .checkbox-label {{
    align-items: center;
    color: #3d4856;
    display: inline-flex;
    gap: 7px;
    font-size: 0.88rem;
    font-weight: 600;
  }}
  .control-button {{
    border: 1px solid #cbd4df;
    border-radius: 6px;
    background: #ffffff;
    color: #20242c;
    cursor: pointer;
    font: inherit;
    font-size: 0.86rem;
    font-weight: 700;
    padding: 8px 11px;
  }}
  .chart-card {{ padding: 16px; margin-bottom: 16px; }}
  .element-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
    gap: 16px;
  }}
  .element-card {{ min-width: 0; }}
  .element-meta {{
    color: #657181;
    display: flex;
    flex-wrap: wrap;
    gap: 6px 12px;
    font-size: 0.82rem;
    margin-top: 6px;
  }}
  .element-detail {{
    border-top: 1px solid #edf0f3;
    display: grid;
    gap: 6px 12px;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    margin-top: 10px;
    padding-top: 10px;
  }}
  .detail-label {{
    color: #657181;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0;
    text-transform: uppercase;
  }}
  .detail-value {{
    color: #20242c;
    font-size: 0.84rem;
    margin-top: 2px;
    overflow-wrap: anywhere;
  }}
  .chart-head {{
    align-items: flex-start;
    display: flex;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
  }}
  .plotly-chart {{ width: 100%; height: 380px; }}
  .profile-plots {{
    display: grid;
    gap: 16px;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  }}
  .cell-plot-title {{
    color: #3d4856;
    font-size: 0.86rem;
    font-weight: 700;
    margin: 4px 0 6px;
  }}
  .cell-profile-chart {{ height: 320px; }}
  .element-plot-chart {{ height: 280px; }}
  .trace-list {{
    border-top: 1px solid #edf0f3;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
    gap: 6px 12px;
    margin-top: 10px;
    max-height: 160px;
    overflow: auto;
    padding-top: 10px;
  }}
  .trace-item {{
    align-items: center;
    color: #3d4856;
    display: flex;
    gap: 7px;
    min-width: 0;
    font-size: 0.82rem;
  }}
  .trace-name {{ overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
  .trace-pill {{
    background: #eef2f6;
    border-radius: 999px;
    color: #657181;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 2px 6px;
  }}
  .empty-state {{
    background: #ffffff;
    border: 1px dashed #cbd4df;
    border-radius: 8px;
    color: #657181;
    padding: 28px;
    text-align: center;
  }}
  .dataset-list {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 10px;
    margin-top: 12px;
  }}
  .dataset-card {{
    border: 1px solid #edf0f3;
    border-radius: 8px;
    padding: 12px;
  }}
  .dataset-title {{ font-weight: 700; }}
  .dataset-meta {{ color: #657181; font-size: 0.82rem; margin-top: 4px; }}
  @media (max-width: 820px) {{
    header {{ padding: 18px 18px; }}
    main {{ padding: 18px 14px 28px; }}
    .header-inner {{ align-items: flex-start; flex-direction: column; }}
    .time-range {{ white-space: normal; }}
    .overview-grid {{ grid-template-columns: 1fr; }}
    .plotly-chart {{ height: 330px; }}
    .cell-profile-chart {{ height: 300px; }}
    .search-input {{ min-width: 100%; }}
    .select-input {{ min-width: 100%; }}
  }}
</style>
</head>
<body>
<header>
  <div class="header-inner">
    <div>
      <div class="kicker">chemunited-sim</div>
      <h1>Dashboard - {safe_stem}</h1>
    </div>
    <div class="time-range">
      t: {_format_number(t_min)} s - {_format_number(t_max)} s
    </div>
  </div>
</header>
<main>
  <section class="metrics" aria-label="Simulation summary">
    {metric_cards}
  </section>
  <nav class="tabs" aria-label="Dashboard sections">
    <button class="tab-button active" data-tab="components">Components</button>
    <button class="tab-button" data-tab="edges">Edges</button>
    <button class="tab-button" data-tab="overview">Overview</button>
    <button class="tab-button" data-tab="signals">Signals</button>
    <button class="tab-button" data-tab="cells">Pipe Cells</button>
  </nav>

  <section class="tab-panel active" data-panel="components">
    <div class="toolbar">
      <input
        class="search-input"
        data-component-search
        type="search"
        placeholder="Search components, nodes, edges, species"
      >
      <button class="control-button" data-reset-components>Reset components</button>
    </div>
    <div id="component-summary" class="panel-subtitle"></div>
    <div id="component-explorer" class="element-grid"></div>
  </section>

  <section class="tab-panel" data-panel="edges">
    <div class="toolbar">
      <input
        class="search-input"
        data-edge-search
        type="search"
        placeholder="Search edges, endpoints, phases, species"
      >
      <select class="select-input" data-edge-time aria-label="Snapshot time"></select>
      <button class="control-button" data-reset-edges>Reset edges</button>
    </div>
    <div id="edge-summary" class="panel-subtitle"></div>
    <div id="edge-explorer" class="element-grid"></div>
  </section>

  <section class="tab-panel" data-panel="overview">
    <div class="overview-grid">
      <div class="panel">
        <h2>Simulation Metadata</h2>
        <div class="panel-subtitle">Values stored in the recorder meta table.</div>
        <table><tbody>{meta_rows}</tbody></table>
      </div>
      <div class="panel">
        <h2>Recorded Datasets</h2>
        <div class="panel-subtitle">
          Trace counts and default visibility by section.
        </div>
        <div id="dataset-summary" class="dataset-list"></div>
      </div>
    </div>
  </section>

  {_render_signals_tab()}
  {_render_cell_tab()}
</main>
<script id="dashboard-data" type="application/json">{payload_json}</script>
<script>
(() => {{
  const payload = JSON.parse(document.getElementById("dashboard-data").textContent);
  const chartTabs = ["pressures", "flows", "inventories", "species", "temperatures"];
  const tabs = ["components", "edges", "overview", "signals", "cells"];
  const components = payload.components || [];
  const edges = payload.edges || [];
  const cellProfiles = payload.cellProfiles || {{ times: [], edges: [] }};
  const cellTimes = cellProfiles.times || [];
  const colorway = [
    "#0b5cad", "#b33f62", "#2f855a", "#b7791f", "#5a4fcf",
    "#0f766e", "#c2410c", "#4a5568", "#7c3aed", "#0369a1"
  ];
  const latestCellTime = cellTimes.length ? cellTimes[cellTimes.length - 1].key : "";
  const state = {{
    activeTab: "components",
    componentQuery: "",
    edgeQuery: "",
    edgeTimeKey: latestCellTime,
    signalQuery: "",
    signalShowFlat: false,
    cellQuery: "",
    cellTimeKey: latestCellTime,
    visibility: {{}}
  }};

  function traceKey(chart, trace) {{
    return `${{chart.id}}::${{trace.name}}`;
  }}

  function defaultVisible(chart, trace) {{
    if (chart.allFlat) return true;
    return Boolean(trace.defaultVisible);
  }}

  function isVisible(chart, trace) {{
    const key = traceKey(chart, trace);
    if (!(key in state.visibility)) {{
      state.visibility[key] = defaultVisible(chart, trace);
    }}
    return state.visibility[key];
  }}

  function setTab(tab) {{
    state.activeTab = tab;
    document.querySelectorAll(".tab-button").forEach((button) => {{
      button.classList.toggle("active", button.dataset.tab === tab);
    }});
    document.querySelectorAll(".tab-panel").forEach((panel) => {{
      panel.classList.toggle("active", panel.dataset.panel === tab);
    }});
    if (tab === "components") {{
      renderComponents();
    }} else if (tab === "edges") {{
      renderEdges();
    }} else if (tab === "signals") {{
      renderSignals();
    }} else if (tab === "cells") {{
      renderCells();
    }}
  }}

  function formatNumber(value) {{
    if (value === null || value === undefined || Number.isNaN(value)) return "n/a";
    const absValue = Math.abs(value);
    if (absValue !== 0 && (absValue < 0.001 || absValue >= 100000)) {{
      return Number(value).toExponential(3);
    }}
    return Number(value).toLocaleString(undefined, {{ maximumSignificantDigits: 5 }});
  }}

  function chartSubtitle(chart, traces) {{
    const visibleCount = traces.filter((trace) => isVisible(chart, trace)).length;
    const flatCount = chart.traces.filter((trace) => trace.flat).length;
    return `${{visibleCount}} visible of ${{chart.traces.length}} traces` +
      (flatCount ? `, ${{flatCount}} flat` : "");
  }}

  function filteredTraces(chart, tab) {{
    const query = tab === "signals"
      ? state.signalQuery.trim().toLowerCase()
      : "";
    return chart.traces.filter((trace) => {{
      const matches = !query ||
        trace.name.toLowerCase().includes(query) ||
        chart.title.toLowerCase().includes(query);
      const allowedFlat = tab === "signals"
        ? state.signalShowFlat || !trace.flat || chart.allFlat
        : !trace.flat || chart.allFlat;
      return matches && allowedFlat;
    }});
  }}

  function renderSignals() {{
    const container = document.getElementById("charts-signals");
    const summary = document.getElementById("signal-summary");
    const query = state.signalQuery.trim().toLowerCase();
    const charts = payload.charts.filter((chart) => {{
      if (!query) return true;
      const haystack = [
        chart.title,
        chart.tab,
        ...chart.traces.map((trace) => trace.name)
      ].join(" ").toLowerCase();
      return haystack.includes(query);
    }});
    container.innerHTML = "";
    if (!charts.length) {{
      summary.textContent = "";
      container.appendChild(emptyState("No signal charts match this filter."));
      return;
    }}
    const traceCount = charts.reduce((sum, chart) => sum + chart.traces.length, 0);
    summary.textContent = `${{charts.length}} chart(s), ${{traceCount}} trace(s)`;
    charts.forEach((chart) => renderChart(container, chart, "signals"));
  }}

  function renderChart(container, chart, tab) {{
    const card = document.createElement("article");
    card.className = "chart-card";
    const plotId = `plot-${{chart.id}}`;
    const traces = filteredTraces(chart, tab);

    card.innerHTML = `
      <div class="chart-head">
        <div>
          <h2>${{escapeHtml(chart.title)}}</h2>
          <div class="chart-meta">${{escapeHtml(chartSubtitle(chart, traces))}}</div>
        </div>
        <button class="control-button" data-reset-chart="${{chart.id}}">
          Reset traces
        </button>
      </div>
      <div id="${{plotId}}" class="plotly-chart"></div>
      <div class="trace-list" data-trace-list="${{chart.id}}"></div>
    `;
    container.appendChild(card);

    card.querySelector("[data-reset-chart]").addEventListener("click", () => {{
      chart.traces.forEach((trace) => {{
        state.visibility[traceKey(chart, trace)] = defaultVisible(chart, trace);
      }});
      if (tab === "signals") {{
        renderSignals();
      }}
    }});

    renderTraceList(card.querySelector("[data-trace-list]"), chart, traces, tab);
    renderPlot(plotId, chart, traces);
  }}

  function renderTraceList(container, chart, traces, tab) {{
    if (!traces.length) {{
      container.innerHTML =
        `<div class="empty-state">No traces match this filter.</div>`;
      return;
    }}
    traces.forEach((trace) => {{
      const label = document.createElement("label");
      label.className = "trace-item";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = isVisible(chart, trace);
      checkbox.addEventListener("change", () => {{
        state.visibility[traceKey(chart, trace)] = checkbox.checked;
        if (tab === "signals") {{
          renderSignals();
        }}
      }});
      const name = document.createElement("span");
      name.className = "trace-name";
      name.textContent = trace.name;
      label.appendChild(checkbox);
      label.appendChild(name);
      if (trace.flat) {{
        const pill = document.createElement("span");
        pill.className = "trace-pill";
        pill.textContent = "flat";
        label.appendChild(pill);
      }}
      container.appendChild(label);
    }});
  }}

  function renderPlot(plotId, chart, traces) {{
    const visible = traces.filter((trace) => isVisible(chart, trace));
    const plotTraces = visible.map((trace) => ({{
      x: trace.x,
      y: trace.y,
      mode: "lines",
      name: trace.name,
      type: "scatter",
      line: {{ width: trace.flat ? 1.4 : 2.2 }},
      hovertemplate:
        "%{{fullData.name}}<br>t=%{{x:.6g}} s" +
        "<br>value=%{{y:.6g}}<extra></extra>"
    }}));
    const layout = {{
      autosize: true,
      colorway,
      hovermode: "x unified",
      margin: {{ t: 12, r: 18, b: 54, l: 68 }},
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      xaxis: {{
        title: {{ text: chart.xLabel, standoff: 8 }},
        gridcolor: "#e9edf2",
        zerolinecolor: "#cbd4df"
      }},
      yaxis: {{
        title: {{ text: chart.yLabel, standoff: 10 }},
        gridcolor: "#e9edf2",
        zerolinecolor: "#cbd4df"
      }},
      legend: {{
        orientation: "h",
        y: -0.24,
        x: 0,
        font: {{ size: 11 }}
      }}
    }};
    const config = {{
      displaylogo: false,
      responsive: true,
      scrollZoom: true,
      modeBarButtonsToRemove: ["lasso2d", "select2d"]
    }};
    Plotly.react(plotId, plotTraces, layout, config);
  }}

  function renderComponents() {{
    const container = document.getElementById("component-explorer");
    const summary = document.getElementById("component-summary");
    const query = state.componentQuery.trim().toLowerCase();
    container.innerHTML = "";
    const visible = components.filter((component) =>
      matchesElement(component, query)
    );
    summary.textContent =
      `${{visible.length}} component(s), ${{components.length}} total`;
    if (!visible.length) {{
      container.appendChild(emptyState(payload.emptyStates.components));
      return;
    }}
    visible.forEach((component, index) => {{
      renderElementCard(container, component, "component", index);
    }});
  }}

  function renderEdges() {{
    const container = document.getElementById("edge-explorer");
    const summary = document.getElementById("edge-summary");
    const query = state.edgeQuery.trim().toLowerCase();
    container.innerHTML = "";
    const visible = edges.filter((edge) => matchesElement(edge, query));
    summary.textContent = `${{visible.length}} edge(s), ${{edges.length}} total`;
    if (!visible.length) {{
      container.appendChild(emptyState(payload.emptyStates.edges));
      return;
    }}
    visible.forEach((edge, index) => {{
      renderElementCard(container, edge, "edge", index);
    }});
  }}

  function matchesElement(element, query) {{
    if (!query) return true;
    const signalText = (element.signals || []).flatMap((group) => [
      group.title,
      ...(group.traces || []).map((trace) => trace.name)
    ]);
    const profile = element.cellProfile;
    const profileText = profile
      ? [
          ...(profile.phases || []),
          ...(profile.species || []).map((item) => item.name)
        ]
      : [];
    const haystack = [
      element.id,
      element.type,
      element.role,
      element.origin,
      element.destination,
      element.component,
      ...(element.nodes || []),
      ...(element.inventories || []),
      ...(element.edges || []),
      ...signalText,
      ...profileText
    ].filter(Boolean).join(" ").toLowerCase();
    return haystack.includes(query);
  }}

  function renderElementCard(container, element, kind, index) {{
    const card = document.createElement("article");
    card.className = "chart-card element-card";
    const groups = element.signals || [];
    const plotPrefix = `${{kind}}-${{index}}`;
    card.innerHTML = `
      <div class="chart-head">
        <div>
          <h2>${{escapeHtml(element.id)}}</h2>
          <div class="chart-meta">${{escapeHtml(elementSubtitle(element, kind))}}</div>
        </div>
      </div>
      ${{elementDetailHtml(element, kind)}}
      <div class="profile-plots" data-element-plots></div>
      <div data-element-cell-profile></div>
    `;
    container.appendChild(card);
    const plotContainer = card.querySelector("[data-element-plots]");
    if (!groups.length) {{
      plotContainer.replaceWith(emptyState("No time-series signals for this element."));
    }} else {{
      groups.forEach((group, groupIndex) => {{
        const wrap = document.createElement("div");
        wrap.className = "cell-plot";
        const plotId = `element-${{plotPrefix}}-${{groupIndex}}`;
        wrap.innerHTML = `
          <div class="cell-plot-title">${{escapeHtml(group.title)}}</div>
          <div id="${{plotId}}" class="plotly-chart element-plot-chart"></div>
        `;
        plotContainer.appendChild(wrap);
        renderElementPlot(plotId, group);
      }});
    }}
    if (kind === "edge" && element.cellProfile) {{
      renderInlineCellProfile(
        card.querySelector("[data-element-cell-profile]"),
        element.cellProfile,
        index
      );
    }}
  }}

  function elementSubtitle(element, kind) {{
    if (kind === "component") {{
      return `${{element.type}} · ${{(element.nodes || []).length}} node(s) · ` +
        `${{(element.edges || []).length}} edge(s)`;
    }}
    const external = element.external === null || element.external === undefined
      ? "recorded edge"
      : (element.external ? "external edge" : "internal edge");
    return `${{element.role}} · ${{external}}`;
  }}

  function elementDetailHtml(element, kind) {{
    const rows = kind === "component" ? [
      ["Type", element.type],
      ["Nodes", (element.nodes || []).join(", ")],
      ["Inventories", (element.inventories || []).join(", ") || "none"],
      ["Edges", (element.edges || []).join(", ") || "none"]
    ] : [
      ["Origin", element.origin || "unknown"],
      ["Destination", element.destination || "unknown"],
      ["Component", element.component || "external tubing"],
      ["Length", element.length === null || element.length === undefined
        ? "n/a" : `${{formatNumber(element.length)}} m`],
      ["Diameter", element.diameter === null || element.diameter === undefined
        ? "n/a" : `${{formatNumber(element.diameter)}} m`]
    ];
    return `
      <div class="element-detail">
        ${{rows.map(([label, value]) => `
          <div>
            <div class="detail-label">${{escapeHtml(label)}}</div>
            <div class="detail-value">${{escapeHtml(value)}}</div>
          </div>
        `).join("")}}
      </div>
    `;
  }}

  function renderElementPlot(plotId, group) {{
    const traces = (group.traces || []).map((trace) => ({{
      x: trace.x,
      y: trace.y,
      mode: "lines",
      name: trace.name,
      type: "scatter",
      line: {{ width: trace.flat ? 1.4 : 2.2 }},
      hovertemplate:
        "%{{fullData.name}}<br>t=%{{x:.6g}} s" +
        "<br>value=%{{y:.6g}}<extra></extra>"
    }}));
    const layout = {{
      autosize: true,
      colorway,
      hovermode: "x unified",
      margin: {{ t: 12, r: 18, b: 54, l: 62 }},
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      xaxis: {{
        title: {{ text: "Simulation time (s)", standoff: 8 }},
        gridcolor: "#e9edf2",
        zerolinecolor: "#cbd4df"
      }},
      yaxis: {{
        title: {{ text: group.yLabel, standoff: 8 }},
        gridcolor: "#e9edf2",
        zerolinecolor: "#cbd4df"
      }},
      legend: {{
        orientation: "h",
        y: -0.25,
        x: 0,
        font: {{ size: 11 }}
      }}
    }};
    Plotly.react(plotId, traces, layout, plotConfig());
  }}

  function renderInlineCellProfile(container, edge, index) {{
    if (!cellTimes.length) return;
    const selected = cellTimes.find((time) => time.key === state.edgeTimeKey) ||
      cellTimes[cellTimes.length - 1];
    state.edgeTimeKey = selected.key;
    const snapshot = edge.snapshots[selected.key];
    if (!snapshot) return;
    const statePlotId = `edge-cell-state-${{index}}`;
    const contentPlotId = `edge-cell-content-${{index}}`;
    container.innerHTML = `
      <div class="profile-plots">
        <div class="cell-plot">
          <div class="cell-plot-title">
            Cell state at ${{escapeHtml(selected.label)}}
          </div>
          <div id="${{statePlotId}}" class="plotly-chart cell-profile-chart"></div>
        </div>
        <div class="cell-plot">
          <div class="cell-plot-title">
            Cell content at ${{escapeHtml(selected.label)}}
          </div>
          <div id="${{contentPlotId}}" class="plotly-chart cell-profile-chart"></div>
        </div>
      </div>
    `;
    renderCellStatePlot(statePlotId, edge, snapshot);
    if (!renderCellContentPlot(contentPlotId, edge, snapshot)) {{
      document.getElementById(contentPlotId).replaceWith(
        emptyState("No cell_content rows at this snapshot.")
      );
    }}
  }}

  function populateCellTimeSelect() {{
    const select = document.querySelector("[data-cell-time]");
    select.innerHTML = "";
    if (!cellTimes.length) {{
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No snapshots";
      select.appendChild(option);
      select.disabled = true;
      return;
    }}
    select.disabled = false;
    cellTimes.forEach((time) => {{
      const option = document.createElement("option");
      option.value = time.key;
      option.textContent = time.label;
      select.appendChild(option);
    }});
    select.value = state.cellTimeKey;
  }}

  function populateEdgeTimeSelect() {{
    const select = document.querySelector("[data-edge-time]");
    select.innerHTML = "";
    if (!cellTimes.length) {{
      const option = document.createElement("option");
      option.value = "";
      option.textContent = "No snapshots";
      select.appendChild(option);
      select.disabled = true;
      return;
    }}
    select.disabled = false;
    cellTimes.forEach((time) => {{
      const option = document.createElement("option");
      option.value = time.key;
      option.textContent = time.label;
      select.appendChild(option);
    }});
    select.value = state.edgeTimeKey;
  }}

  function renderCells() {{
    const container = document.getElementById("cell-profiles");
    const summary = document.getElementById("cell-profile-summary");
    container.innerHTML = "";

    if (!cellTimes.length || !cellProfiles.edges.length) {{
      summary.textContent = "";
      container.appendChild(emptyState(payload.emptyStates.cells));
      return;
    }}

    const selected = cellTimes.find((time) => time.key === state.cellTimeKey) ||
      cellTimes[cellTimes.length - 1];
    state.cellTimeKey = selected.key;
    const query = state.cellQuery.trim().toLowerCase();
    const edges = cellProfiles.edges.filter((edge) =>
      edge.snapshots[selected.key] && matchesCellEdge(edge, query)
    );

    summary.textContent =
      `${{edges.length}} edge(s), ${{cellProfiles.edges.length}} total, ` +
      `t=${{selected.label}}`;
    if (!edges.length) {{
      container.appendChild(emptyState("No pipe-cell profiles match this filter."));
      return;
    }}
    edges.forEach((edge, index) =>
      renderCellEdge(container, edge, selected.key, index)
    );
  }}

  function matchesCellEdge(edge, query) {{
    if (!query) return true;
    const haystack = [
      edge.edgeId,
      ...(edge.phases || []),
      ...(edge.species || []).map((item) => item.name)
    ].join(" ").toLowerCase();
    return haystack.includes(query);
  }}

  function renderCellEdge(container, edge, timeKey, index) {{
    const snapshot = edge.snapshots[timeKey];
    const card = document.createElement("article");
    card.className = "chart-card";
    const statePlotId = `cell-state-${{index}}`;
    const contentPlotId = `cell-content-${{index}}`;
    const phaseLabel = `${{edge.phases.length}} phase` +
      (edge.phases.length === 1 ? "" : "s");
    const speciesLabel = `${{edge.species.length}} species trace` +
      (edge.species.length === 1 ? "" : "s");

    card.innerHTML = `
      <div class="chart-head">
        <div>
          <h2>${{escapeHtml(edge.edgeId)}}</h2>
          <div class="chart-meta">
            ${{edge.cellCount}} cells, ${{phaseLabel}}, ${{speciesLabel}}
          </div>
        </div>
      </div>
      <div class="profile-plots">
        <div class="cell-plot">
          <div class="cell-plot-title">Cell state</div>
          <div id="${{statePlotId}}" class="plotly-chart cell-profile-chart"></div>
        </div>
        <div class="cell-plot">
          <div class="cell-plot-title">Cell content</div>
          <div id="${{contentPlotId}}" class="plotly-chart cell-profile-chart"></div>
        </div>
      </div>
    `;
    container.appendChild(card);
    renderCellStatePlot(statePlotId, edge, snapshot);
    if (!renderCellContentPlot(contentPlotId, edge, snapshot)) {{
      document.getElementById(contentPlotId).replaceWith(
        emptyState("No cell_content rows at this snapshot.")
      );
    }}
  }}

  function renderCellStatePlot(plotId, edge, snapshot) {{
    const x = cellX(edge);
    const customdata = cellCustomData(edge);
    const traces = [];
    (edge.phases || []).forEach((phase, phaseIndex) => {{
      const fractions = snapshot.phaseFractions[phase] || x.map(() => 0);
      const temperatures = snapshot.temperatures[phase] || x.map(() => null);
      if (hasNonZero(fractions) || hasFiniteValue(temperatures)) {{
        traces.push({{
          x,
          y: fractions,
          customdata,
          mode: "lines+markers",
          name: `${{phase}} fraction`,
          type: "scatter",
          line: {{ width: 2.2, color: colorway[phaseIndex % colorway.length] }},
          marker: {{ size: 5 }},
          hovertemplate:
            "%{{fullData.name}}<br>cell=%{{customdata[0]}}" +
            "<br>x=%{{x:.6g}}<br>fraction=%{{y:.6g}}<extra></extra>"
        }});
      }}
      if (hasFiniteValue(temperatures)) {{
        traces.push({{
          x,
          y: temperatures,
          customdata,
          mode: "lines+markers",
          name: `${{phase}} temperature`,
          type: "scatter",
          yaxis: "y2",
          line: {{
            dash: "dot",
            width: 1.8,
            color: colorway[(phaseIndex + 5) % colorway.length]
          }},
          marker: {{ size: 4 }},
          hovertemplate:
            "%{{fullData.name}}<br>cell=%{{customdata[0]}}" +
            "<br>x=%{{x:.6g}}<br>temperature=%{{y:.6g}} K<extra></extra>"
        }});
      }}
    }});
    const layout = {{
      autosize: true,
      colorway,
      hovermode: "closest",
      margin: {{ t: 12, r: 72, b: 54, l: 58 }},
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      xaxis: {{
        title: {{ text: edge.xLabel, standoff: 8 }},
        gridcolor: "#e9edf2",
        zerolinecolor: "#cbd4df"
      }},
      yaxis: {{
        title: {{ text: "Phase fraction", standoff: 8 }},
        gridcolor: "#e9edf2",
        range: [-0.02, 1.02],
        zerolinecolor: "#cbd4df"
      }},
      yaxis2: {{
        title: {{ text: "Temperature (K)", standoff: 8 }},
        overlaying: "y",
        side: "right",
        showgrid: false,
        zeroline: false
      }},
      legend: {{
        orientation: "h",
        y: -0.25,
        x: 0,
        font: {{ size: 11 }}
      }}
    }};
    Plotly.react(plotId, traces, layout, plotConfig());
  }}

  function renderCellContentPlot(plotId, edge, snapshot) {{
    const x = cellX(edge);
    const customdata = cellCustomData(edge);
    const traces = [];
    (edge.species || []).forEach((item, speciesIndex) => {{
      const values = snapshot.contents[item.key] || x.map(() => 0);
      if (!hasNonZero(values)) return;
      traces.push({{
        x,
        y: values,
        customdata,
        mode: "lines+markers",
        name: item.name,
        type: "scatter",
        line: {{ width: 2.1, color: colorway[speciesIndex % colorway.length] }},
        marker: {{ size: 5 }},
        hovertemplate:
          "%{{fullData.name}}<br>cell=%{{customdata[0]}}" +
          "<br>x=%{{x:.6g}}<br>moles=%{{y:.6g}} mol<extra></extra>"
      }});
    }});
    if (!traces.length) return false;
    const layout = {{
      autosize: true,
      colorway,
      hovermode: "closest",
      margin: {{ t: 12, r: 18, b: 54, l: 68 }},
      paper_bgcolor: "#ffffff",
      plot_bgcolor: "#ffffff",
      xaxis: {{
        title: {{ text: edge.xLabel, standoff: 8 }},
        gridcolor: "#e9edf2",
        zerolinecolor: "#cbd4df"
      }},
      yaxis: {{
        title: {{ text: "Moles (mol)", standoff: 10 }},
        gridcolor: "#e9edf2",
        zerolinecolor: "#cbd4df"
      }},
      legend: {{
        orientation: "h",
        y: -0.25,
        x: 0,
        font: {{ size: 11 }}
      }}
    }};
    Plotly.react(plotId, traces, layout, plotConfig());
    return true;
  }}

  function cellX(edge) {{
    return (edge.cells || []).map((cell) =>
      edge.xLabel === "Cell position (m)" ? cell.center : cell.index
    );
  }}

  function cellCustomData(edge) {{
    return (edge.cells || []).map((cell) => [
      cell.index,
      cell.position,
      cell.length
    ]);
  }}

  function hasFiniteValue(values) {{
    return values.some((value) =>
      value !== null && value !== undefined && Number.isFinite(Number(value))
    );
  }}

  function hasNonZero(values) {{
    return values.some((value) =>
      value !== null &&
      value !== undefined &&
      Number.isFinite(Number(value)) &&
      Math.abs(Number(value)) > 0
    );
  }}

  function plotConfig() {{
    return {{
      displaylogo: false,
      responsive: true,
      scrollZoom: true,
      modeBarButtonsToRemove: ["lasso2d", "select2d"]
    }};
  }}

  function emptyState(text) {{
    const node = document.createElement("div");
    node.className = "empty-state";
    node.textContent = text;
    return node;
  }}

  function renderDatasetSummary() {{
    const container = document.getElementById("dataset-summary");
    container.innerHTML = "";
    const labels = {{
      pressures: "Pressures",
      flows: "Flows",
      inventories: "Inventories",
      species: "Species",
      temperatures: "Temperatures"
    }};
    chartTabs.forEach((tab) => {{
      const charts = payload.charts.filter((chart) => chart.tab === tab);
      const traceCount = charts.reduce((sum, chart) => sum + chart.traces.length, 0);
      const defaultCount = charts.reduce(
        (sum, chart) => sum + chart.traces
          .filter((trace) => defaultVisible(chart, trace)).length,
        0
      );
      const flatCount = charts.reduce(
        (sum, chart) => sum + chart.traces.filter((trace) => trace.flat).length,
        0
      );
      const card = document.createElement("div");
      card.className = "dataset-card";
      card.innerHTML = `
        <div class="dataset-title">${{labels[tab]}}</div>
        <div class="dataset-meta">
          ${{charts.length}} chart(s), ${{traceCount}} trace(s)
        </div>
        <div class="dataset-meta">
          ${{defaultCount}} shown by default, ${{flatCount}} flat
        </div>
      `;
      container.appendChild(card);
    }});
    const cellEdges = cellProfiles.edges || [];
    const cellCount = cellEdges.reduce((sum, edge) => sum + edge.cellCount, 0);
    const cellSpecies = cellEdges.reduce(
      (sum, edge) => sum + edge.species.length,
      0
    );
    const cellCard = document.createElement("div");
    cellCard.className = "dataset-card";
    cellCard.innerHTML = `
      <div class="dataset-title">Pipe Cells</div>
      <div class="dataset-meta">
        ${{cellEdges.length}} edge(s), ${{cellCount}} cell(s)
      </div>
      <div class="dataset-meta">
        ${{cellTimes.length}} snapshot(s), ${{cellSpecies}} species trace(s)
      </div>
    `;
    container.appendChild(cellCard);
  }}

  function escapeHtml(value) {{
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }}

  document.querySelectorAll(".tab-button").forEach((button) => {{
    button.addEventListener("click", () => setTab(button.dataset.tab));
  }});
  const componentSearch = document.querySelector("[data-component-search]");
  const componentReset = document.querySelector("[data-reset-components]");
  componentSearch.addEventListener("input", () => {{
    state.componentQuery = componentSearch.value;
    renderComponents();
  }});
  componentReset.addEventListener("click", () => {{
    state.componentQuery = "";
    componentSearch.value = "";
    renderComponents();
  }});

  const edgeSearch = document.querySelector("[data-edge-search]");
  const edgeTimeSelect = document.querySelector("[data-edge-time]");
  const edgeReset = document.querySelector("[data-reset-edges]");
  edgeSearch.addEventListener("input", () => {{
    state.edgeQuery = edgeSearch.value;
    renderEdges();
  }});
  edgeTimeSelect.addEventListener("change", () => {{
    state.edgeTimeKey = edgeTimeSelect.value;
    renderEdges();
  }});
  edgeReset.addEventListener("click", () => {{
    state.edgeQuery = "";
    state.edgeTimeKey = latestCellTime;
    edgeSearch.value = "";
    edgeTimeSelect.value = latestCellTime;
    renderEdges();
  }});

  const signalSearch = document.querySelector("[data-signal-search]");
  const signalFlatToggle = document.querySelector("[data-show-flat-signals]");
  const signalReset = document.querySelector("[data-reset-signals]");
  signalSearch.addEventListener("input", () => {{
    state.signalQuery = signalSearch.value;
    renderSignals();
  }});
  signalFlatToggle.addEventListener("change", () => {{
    state.signalShowFlat = signalFlatToggle.checked;
    renderSignals();
  }});
  signalReset.addEventListener("click", () => {{
    state.signalQuery = "";
    state.signalShowFlat = false;
    signalSearch.value = "";
    signalFlatToggle.checked = false;
    payload.charts.forEach((chart) => chart.traces.forEach((trace) => {{
      state.visibility[traceKey(chart, trace)] = defaultVisible(chart, trace);
    }}));
    renderSignals();
  }});

  const cellSearch = document.querySelector("[data-cell-search]");
  const cellTimeSelect = document.querySelector("[data-cell-time]");
  const cellReset = document.querySelector("[data-reset-cells]");
  cellSearch.addEventListener("input", () => {{
    state.cellQuery = cellSearch.value;
    renderCells();
  }});
  cellTimeSelect.addEventListener("change", () => {{
    state.cellTimeKey = cellTimeSelect.value;
    renderCells();
  }});
  cellReset.addEventListener("click", () => {{
    state.cellQuery = "";
    state.cellTimeKey = latestCellTime;
    cellSearch.value = "";
    cellTimeSelect.value = latestCellTime;
    renderCells();
  }});

  populateEdgeTimeSelect();
  populateCellTimeSelect();
  renderComponents();
  renderDatasetSummary();
}})();
</script>
</body>
</html>"""


def _build_charts(
    *,
    node_pressures: dict[str, list],
    edge_flows: dict[str, list],
    inv_states: dict[str, list],
    species_moles: dict[str, dict[str, list]],
    cell_temps: dict[str, list],
) -> list[ChartSpec]:
    charts: list[ChartSpec] = []
    charts.append(
        _make_line_chart(
            chart_id="node_pressures",
            tab="pressures",
            title="Node Pressures",
            series={
                nid: ([t for t, _ in pts], [p for _, p in pts])
                for nid, pts in node_pressures.items()
            },
            x_label="Simulation time (s)",
            y_label="Pressure (bar)",
        )
    )
    charts.append(
        _make_line_chart(
            chart_id="edge_flows",
            tab="flows",
            title="Edge Flow Rates",
            series={
                eid: ([t for t, _ in pts], [f for _, f in pts])
                for eid, pts in edge_flows.items()
            },
            x_label="Simulation time (s)",
            y_label="Flow rate (mL/min)",
        )
    )
    charts.append(
        _make_line_chart(
            chart_id="inv_temperatures",
            tab="temperatures",
            title="Inventory Temperatures",
            series={
                nid: ([t for t, _, _ in pts], [temp for _, _, temp in pts])
                for nid, pts in inv_states.items()
            },
            x_label="Simulation time (s)",
            y_label="Temperature (K)",
        )
    )
    charts.append(
        _make_line_chart(
            chart_id="inv_pressures",
            tab="inventories",
            title="Inventory Pressures",
            series={
                nid: ([t for t, _, _ in pts], [pressure for _, pressure, _ in pts])
                for nid, pts in inv_states.items()
            },
            x_label="Simulation time (s)",
            y_label="Pressure (bar)",
        )
    )
    for i, (group_key, species_dict) in enumerate(sorted(species_moles.items())):
        charts.append(
            _make_line_chart(
                chart_id=f"species_{i}",
                tab="species",
                title=f"Species Moles - {group_key}",
                series={
                    sid: ([t for t, _ in pts], [moles for _, moles in pts])
                    for sid, pts in species_dict.items()
                },
                x_label="Simulation time (s)",
                y_label="Moles (mol)",
            )
        )
    charts.append(
        _make_line_chart(
            chart_id="cell_temps",
            tab="temperatures",
            title="Edge Average Cell Temperature",
            series={
                eid: ([t for t, _ in pts], [temp for _, temp in pts])
                for eid, pts in cell_temps.items()
            },
            x_label="Simulation time (s)",
            y_label="Temperature (K)",
        )
    )
    return [chart for chart in charts if chart.traces]


def _make_line_chart(
    *,
    chart_id: str,
    tab: str,
    title: str,
    series: dict[str, tuple[list, list]],
    x_label: str,
    y_label: str,
) -> ChartSpec:
    raw_traces: list[_RawTrace] = []
    for name, (xs, ys) in sorted(series.items()):
        y_values = [float(value) for value in ys]
        x_values = [_round_time(float(value)) for value in xs]
        if y_values:
            minimum = min(y_values)
            maximum = max(y_values)
            value_range = maximum - minimum
            max_abs = max(abs(value) for value in y_values)
        else:
            minimum = None
            maximum = None
            value_range = 0.0
            max_abs = 0.0
        flat = value_range <= max(_FLAT_ABS_TOL, _FLAT_REL_TOL * max_abs)
        raw_traces.append(
            {
                "name": name,
                "x": x_values,
                "y": y_values,
                "minimum": minimum,
                "maximum": maximum,
                "range": value_range,
                "max_abs": max_abs,
                "flat": flat,
            }
        )

    all_flat = bool(raw_traces) and all(trace["flat"] for trace in raw_traces)
    traces = [
        TraceSpec(
            name=trace["name"],
            x=trace["x"],
            y=trace["y"],
            minimum=trace["minimum"],
            maximum=trace["maximum"],
            value_range=trace["range"],
            max_abs=trace["max_abs"],
            flat=trace["flat"],
            default_visible=all_flat or not trace["flat"],
        )
        for trace in raw_traces
    ]
    return ChartSpec(
        chart_id=chart_id,
        tab=tab,
        title=title,
        x_label=x_label,
        y_label=y_label,
        traces=traces,
    )


def _build_summary(
    *,
    node_pressures: dict[str, list],
    edge_flows: dict[str, list],
    inv_states: dict[str, list],
    species_moles: dict[str, dict[str, list]],
    cell_temps: dict[str, list],
    cell_profiles: dict[str, Any],
) -> dict[str, Any]:
    all_time_values = {
        t
        for points in _all_point_lists(
            node_pressures, edge_flows, inv_states, species_moles, cell_temps
        )
        for t in _times_from_points(points)
    }
    all_time_values.update(
        float(item["value"]) for item in cell_profiles.get("times", [])
    )
    all_times = sorted(all_time_values)
    t_min = min(all_times, default=0.0)
    t_max = max(all_times, default=0.0)
    pressure_values = [p for pts in node_pressures.values() for _, p in pts]
    pressure_values.extend(p for pts in inv_states.values() for _, p, _ in pts)
    flow_values = [flow for pts in edge_flows.values() for _, flow in pts]
    temp_values = [temp for pts in cell_temps.values() for _, temp in pts]
    temp_values.extend(temp for pts in inv_states.values() for _, _, temp in pts)
    species_ids = {
        species_id
        for species_dict in species_moles.values()
        for species_id in species_dict
    }
    cell_edges = cell_profiles.get("edges", [])
    cell_species = {
        (item["phase"], item["speciesId"])
        for edge in cell_edges
        for item in edge["species"]
    }

    metrics = [
        _metric("Duration", t_max - t_min, "s"),
        _metric("Samples", len(all_times), ""),
        _metric("Nodes", len(node_pressures), ""),
        _metric("Edges", len(edge_flows), ""),
        _metric("Inventories", len(inv_states), ""),
        _metric("Species", len(species_ids), ""),
        _metric("Pipe Edges", len(cell_edges), ""),
        _metric(
            "Pipe Cells",
            sum(int(edge["cellCount"]) for edge in cell_edges),
            "",
        ),
        _metric("Cell Species", len(cell_species), ""),
        _metric(
            "Max Pressure",
            max(pressure_values) if pressure_values else None,
            "bar",
        ),
        _metric(
            "Max Abs Flow",
            max((abs(flow) for flow in flow_values), default=None),
            "mL/min",
        ),
        _metric("Temperature Range", _range_text(temp_values), "K", preformatted=True),
    ]
    return {
        "timeStart": _round_time(t_min),
        "timeEnd": _round_time(t_max),
        "sampleCount": len(all_times),
        "metrics": metrics,
    }


def _all_point_lists(
    node_pressures: dict[str, list],
    edge_flows: dict[str, list],
    inv_states: dict[str, list],
    species_moles: dict[str, dict[str, list]],
    cell_temps: dict[str, list],
) -> list[list]:
    point_lists: list[list] = []
    point_lists.extend(node_pressures.values())
    point_lists.extend(edge_flows.values())
    point_lists.extend(inv_states.values())
    point_lists.extend(cell_temps.values())
    for species_dict in species_moles.values():
        point_lists.extend(species_dict.values())
    return point_lists


def _times_from_points(points: list) -> list[float]:
    return [float(point[0]) for point in points]


def _metric(
    label: str,
    value: float | int | str | None,
    unit: str,
    *,
    preformatted: bool = False,
) -> dict[str, str]:
    if value is None:
        text = "n/a"
    elif preformatted:
        text = str(value)
    elif isinstance(value, int):
        text = f"{value:,}"
    else:
        text = _format_number(float(value))
    return {"label": label, "value": text, "unit": unit}


def _range_text(values: list[float]) -> str | None:
    if not values:
        return None
    return f"{_format_number(min(values))} - {_format_number(max(values))}"


def _render_metric_cards(metrics: list[dict[str, str]]) -> str:
    return "\n".join(
        (
            '<div class="metric-card">'
            f'<div class="metric-label">{html.escape(metric["label"])}</div>'
            f'<div class="metric-value">{html.escape(metric["value"])}'
            f' <span class="metric-unit">{html.escape(metric["unit"])}</span></div>'
            "</div>"
        )
        for metric in metrics
    )


def _render_meta_rows(meta: dict[str, str]) -> str:
    if not meta:
        return '<tr><td colspan="2">No metadata recorded.</td></tr>'
    return "".join(
        f"<tr><td>{html.escape(str(k))}</td><td>{html.escape(str(v))}</td></tr>"
        for k, v in sorted(meta.items())
    )


def _render_chart_tab(
    tab: str, search_placeholder: str, *, show_flat_default: bool = False
) -> str:
    safe_tab = html.escape(tab)
    safe_placeholder = html.escape(search_placeholder)
    checked = " checked" if show_flat_default else ""
    return f"""
  <section class="tab-panel" data-panel="{safe_tab}">
    <div class="toolbar">
      <input
        class="search-input"
        data-search="{safe_tab}"
        type="search"
        placeholder="{safe_placeholder}"
      >
      <label class="checkbox-label">
        <input data-show-flat="{safe_tab}" type="checkbox"{checked}>
        Show flat traces
      </label>
      <button class="control-button" data-reset-tab="{safe_tab}">Reset tab</button>
    </div>
    <div id="charts-{safe_tab}"></div>
  </section>"""


def _render_signals_tab() -> str:
    return """
  <section class="tab-panel" data-panel="signals">
    <div class="toolbar">
      <input
        class="search-input"
        data-signal-search
        type="search"
        placeholder="Search signal charts and traces"
      >
      <label class="checkbox-label">
        <input data-show-flat-signals type="checkbox">
        Show flat traces
      </label>
      <button class="control-button" data-reset-signals>Reset signals</button>
    </div>
    <div id="signal-summary" class="panel-subtitle"></div>
    <div id="charts-signals"></div>
  </section>"""


def _render_cell_tab() -> str:
    return """
  <section class="tab-panel" data-panel="cells">
    <div class="toolbar">
      <input
        class="search-input"
        data-cell-search
        type="search"
        placeholder="Search pipe-cell profiles"
      >
      <select class="select-input" data-cell-time aria-label="Snapshot time"></select>
      <button class="control-button" data-reset-cells>Reset cells</button>
    </div>
    <div id="cell-profile-summary" class="panel-subtitle"></div>
    <div id="cell-profiles"></div>
  </section>"""


def _json_script_payload(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        data.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _format_number(value: float) -> str:
    abs_value = abs(value)
    if abs_value != 0.0 and (abs_value < 0.001 or abs_value >= 100_000):
        return f"{value:.4g}"
    return f"{value:.6g}"


def _round_time(value: float) -> float:
    return round(value, 10)


def _time_key(value: float) -> str:
    return f"{_round_time(value):.10g}"


def _content_trace_key(phase: str, species_id: str) -> str:
    return json.dumps([phase, species_id], separators=(",", ":"))
