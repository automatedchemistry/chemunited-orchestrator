"""Pyvis export for recorded chemunited-sim snapshots."""

from __future__ import annotations

import html
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from chemunited_core.common.constant import ATMOSPHERE_PRESSURE_PA
from pyvis.network import Network

from ..adapter.models import HydraulicGraph, HydraulicNode


class SnapshotReadError(RuntimeError):
    """Raised when a recorded simulation snapshot cannot be read."""


class NoSnapshotsError(SnapshotReadError):
    """Raised when a simulation database exists but contains no snapshots."""


@dataclass(frozen=True)
class InventorySnapshot:
    """Recorded state for one inventory node at one simulation time."""

    pressure: float
    temperature: float
    phase_volumes: dict[str, float] = field(default_factory=dict)
    species_moles: dict[str, dict[str, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class EdgeCellSnapshot:
    """Recorded cell-state summary for one edge at one simulation time."""

    cell_count: int
    phases: dict[str, float] = field(default_factory=dict)
    average_temperature: float | None = None


@dataclass(frozen=True)
class VisualizationSnapshot:
    """Latest recorded simulation data used by the pyvis renderer."""

    time: float
    pressures: dict[str, float]
    flows: dict[str, float]
    inventories: dict[str, InventorySnapshot] = field(default_factory=dict)
    edge_cells: dict[str, EdgeCellSnapshot] = field(default_factory=dict)


def load_latest_snapshot(db_path: str | os.PathLike) -> VisualizationSnapshot:
    """Read the latest committed recorder snapshot from *db_path*."""
    path = Path(db_path)
    uri = f"file:{path}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        raise SnapshotReadError(f"Could not open simulation DB: {path}") from exc

    try:
        latest = conn.execute("SELECT MAX(time) AS time FROM node_pressure").fetchone()
        if latest is None or latest["time"] is None:
            raise NoSnapshotsError(f"No recorded snapshots in simulation DB: {path}")
        t = float(latest["time"])

        pressures = {
            row["node_id"]: float(row["pressure"])
            for row in conn.execute(
                "SELECT node_id, pressure FROM node_pressure WHERE time = ?",
                (t,),
            )
        }
        flows = {
            row["edge_id"]: float(row["flow_rate"])
            for row in conn.execute(
                "SELECT edge_id, flow_rate FROM edge_flow WHERE time = ?",
                (t,),
            )
        }
        inventories = _read_inventories(conn, t)
        edge_cells = _read_edge_cells(conn, t)
        return VisualizationSnapshot(
            time=t,
            pressures=pressures,
            flows=flows,
            inventories=inventories,
            edge_cells=edge_cells,
        )
    except NoSnapshotsError:
        raise
    except sqlite3.Error as exc:
        raise SnapshotReadError(f"Could not read simulation DB: {path}") from exc
    finally:
        conn.close()


def render_pyvis_html(
    graph: HydraulicGraph,
    components: Iterable[Any],
    snapshot: VisualizationSnapshot,
) -> str:
    """Render *graph* and recorded *snapshot* as standalone pyvis HTML."""
    component_types = {
        comp.name: type(comp).__name__ for comp in components if hasattr(comp, "name")
    }
    pressure_scale = _value_scale(snapshot.pressures.values())
    temperature_scale = _value_scale(_snapshot_temperatures(snapshot))
    max_abs_flow = max((abs(flow) for flow in snapshot.flows.values()), default=0.0)

    net = Network(
        height="900px",
        width="100%",
        directed=True,
        cdn_resources="in_line",
    )
    net.barnes_hut(
        gravity=-4500,
        central_gravity=0.25,
        spring_length=160,
        spring_strength=0.035,
        damping=0.45,
    )
    net.set_options("""
        var options = {
          "nodes": {
            "borderWidth": 1,
            "font": {"size": 15, "face": "arial"}
          },
          "edges": {
            "arrows": {"to": {"enabled": true, "scaleFactor": 0.6}},
            "font": {"size": 10, "align": "middle"},
            "smooth": {"type": "dynamic"}
          },
          "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true
          },
          "physics": {
            "stabilization": {"iterations": 300}
          }
        }
        """)

    for nid, node in sorted(graph.nodes.items()):
        group, shape = _node_visual(graph, nid, node)
        pressure = snapshot.pressures.get(nid)
        temperature = _node_temperature(snapshot, nid)
        background = _blue_scale(pressure, pressure_scale, fallback="#F1EFE8")
        border = _red_scale(temperature, temperature_scale, fallback="#9A9892")
        label = nid.replace(".Inventory", "\nInventory")
        title = _node_title(
            graph=graph,
            node_id=nid,
            node=node,
            component_types=component_types,
            snapshot=snapshot,
            group=group,
        )
        net.add_node(
            nid,
            label=label,
            title=_html_lines(title),
            shape=shape,
            color={
                "background": background,
                "border": border,
                "highlight": {"background": background, "border": border},
            },
            borderWidth=3 if temperature is not None else 1,
        )

    for eid, edge in sorted(graph.edges.items()):
        flow = snapshot.flows.get(eid)
        src = edge.origin_node_id
        dst = edge.destination_node_id
        direction = "origin -> destination"
        if flow is not None and flow < 0:
            src = edge.destination_node_id
            dst = edge.origin_node_id
            direction = "destination -> origin"

        closed = edge.resistance_override is not None
        moving = abs(flow) > 0.0 if flow is not None else False
        edge_temperature = _edge_temperature(snapshot, eid)
        color = _red_scale(edge_temperature, temperature_scale, fallback="#9A9892")
        title = _edge_title(eid, edge, flow, direction, snapshot)

        net.add_edge(
            src,
            dst,
            id=eid,
            title=_html_lines(title),
            width=_flow_width(flow, max_abs_flow),
            color=color,
            dashes=closed or not moving,
        )

    return net.generate_html(notebook=False)


def _read_inventories(
    conn: sqlite3.Connection,
    t: float,
) -> dict[str, InventorySnapshot]:
    inv_rows = list(
        conn.execute(
            "SELECT node_id, pressure, temperature FROM inventory_state WHERE time = ?",
            (t,),
        )
    )
    inventories: dict[str, InventorySnapshot] = {
        row["node_id"]: InventorySnapshot(
            pressure=float(row["pressure"]),
            temperature=float(row["temperature"]),
        )
        for row in inv_rows
    }

    for row in conn.execute(
        """
        SELECT node_id, phase, species_id, moles, volume
        FROM inventory_content
        WHERE time = ?
        ORDER BY node_id, phase, species_id
        """,
        (t,),
    ):
        inv = inventories.setdefault(
            row["node_id"],
            InventorySnapshot(pressure=0.0, temperature=0.0),
        )
        phase = row["phase"]
        inv.phase_volumes[phase] = float(row["volume"])
        if row["species_id"] != "__carrier__":
            species = inv.species_moles.setdefault(phase, {})
            species[row["species_id"]] = float(row["moles"])

    return inventories


def _read_edge_cells(
    conn: sqlite3.Connection,
    t: float,
) -> dict[str, EdgeCellSnapshot]:
    rows = conn.execute(
        """
        SELECT edge_id,
               COUNT(*) AS cell_count,
               AVG(temperature) AS average_temperature
        FROM cell_state
        WHERE time = ?
        GROUP BY edge_id
        """,
        (t,),
    )
    edge_cells = {
        row["edge_id"]: EdgeCellSnapshot(
            cell_count=int(row["cell_count"]),
            average_temperature=(
                float(row["average_temperature"])
                if row["average_temperature"] is not None
                else None
            ),
        )
        for row in rows
    }

    for row in conn.execute(
        """
        SELECT edge_id, phase, SUM(phase_fraction) AS phase_fraction_sum
        FROM cell_state
        WHERE time = ?
        GROUP BY edge_id, phase
        """,
        (t,),
    ):
        edge = edge_cells.get(row["edge_id"])
        if edge is not None:
            edge.phases[row["phase"]] = float(row["phase_fraction_sum"])

    return edge_cells


def _node_visual(
    graph: HydraulicGraph,
    nid: str,
    node: HydraulicNode,
) -> tuple[str, str]:
    if nid in graph.inventory_nodes:
        return "inventory", "box"
    if node.is_hub:
        return "hub", "diamond"
    if node.boundary is not None:
        return "boundary", "ellipse"
    return "internal", "dot"


def _node_title(
    *,
    graph: HydraulicGraph,
    node_id: str,
    node: HydraulicNode,
    component_types: dict[str, str],
    snapshot: VisualizationSnapshot,
    group: str,
) -> list[str]:
    title = [
        f"snapshot time: {snapshot.time:.6g} s",
        f"node: {node_id}",
        f"component: {node.component}",
        f"type: {component_types.get(node.component, 'external')}",
        f"group: {group}",
    ]
    pressure = snapshot.pressures.get(node_id)
    if pressure is not None:
        title.append(f"pressure: {pressure / ATMOSPHERE_PRESSURE_PA:.4f} bar")
    if node.boundary is not None:
        title.append(f"boundary: {node.boundary}")

    inv = snapshot.inventories.get(node_id)
    if inv is not None:
        title.extend(
            [
                f"temperature: {inv.temperature:.3f} K",
                f"inventory pressure: {inv.pressure / ATMOSPHERE_PRESSURE_PA:.4f} bar",
            ]
        )
        for phase, volume in sorted(inv.phase_volumes.items()):
            title.append(f"{phase} volume: {volume * 1e6:.3f} mL")
            species = inv.species_moles.get(phase, {})
            for species_id, moles in sorted(species.items()):
                title.append(f"{phase} {species_id}: {moles:.4e} mol")
    elif node_id in graph.inventory_nodes:
        title.append("inventory: no recorded state at this snapshot")

    return title


def _edge_title(
    edge_id: str,
    edge: Any,
    flow: float | None,
    direction: str,
    snapshot: VisualizationSnapshot,
) -> list[str]:
    title = [
        f"snapshot time: {snapshot.time:.6g} s",
        f"edge: {edge_id}",
        f"structural path: {edge.origin_node_id} -> {edge.destination_node_id}",
        f"displayed direction: {direction}",
        f"role: {edge.role.name}",
        f"component: {edge.component or 'external tubing'}",
        f"external: {edge.is_external}",
        f"length: {edge.length:.4g} m",
        f"diameter: {edge.diameter:.4g} m",
    ]
    if flow is not None:
        title.append(f"flow: {flow * 6e7:+.4f} mL/min")
    if edge.resistance_override is not None:
        title.append(f"resistance override: {edge.resistance_override:.4e} Pa*s/m3")

    cells = snapshot.edge_cells.get(edge_id)
    if cells is not None:
        title.append(f"recorded cells: {cells.cell_count}")
        if cells.average_temperature is not None:
            title.append(f"average cell temperature: {cells.average_temperature:.3f} K")
        for phase, fraction_sum in sorted(cells.phases.items()):
            title.append(f"{phase} phase-fraction sum: {fraction_sum:.4g}")

    return title


def _html_lines(lines: list[str]) -> str:
    return "\n".join(html.escape(line) for line in lines)


def _snapshot_temperatures(snapshot: VisualizationSnapshot) -> list[float]:
    temperatures = [inv.temperature for inv in snapshot.inventories.values()]
    temperatures.extend(
        cells.average_temperature
        for cells in snapshot.edge_cells.values()
        if cells.average_temperature is not None
    )
    return temperatures


def _node_temperature(snapshot: VisualizationSnapshot, node_id: str) -> float | None:
    inv = snapshot.inventories.get(node_id)
    if inv is not None:
        return inv.temperature
    return None


def _edge_temperature(snapshot: VisualizationSnapshot, edge_id: str) -> float | None:
    cells = snapshot.edge_cells.get(edge_id)
    if cells is None:
        return None
    return cells.average_temperature


def _flow_width(flow: float | None, max_abs_flow: float) -> float:
    if flow is None or max_abs_flow <= 0.0:
        return 1.0
    relative = min(1.0, abs(flow) / max_abs_flow)
    return 1.0 + 7.0 * relative**0.5


def _value_scale(values: Iterable[float | None]) -> tuple[float, float] | None:
    finite_values = [value for value in values if value is not None]
    if not finite_values:
        return None
    return min(finite_values), max(finite_values)


def _blue_scale(
    value: float | None,
    scale: tuple[float, float] | None,
    *,
    fallback: str,
) -> str:
    return _scaled_color(
        value=value,
        scale=scale,
        low=(232, 241, 255),
        high=(8, 81, 156),
        fallback=fallback,
    )


def _red_scale(
    value: float | None,
    scale: tuple[float, float] | None,
    *,
    fallback: str,
) -> str:
    return _scaled_color(
        value=value,
        scale=scale,
        low=(255, 240, 240),
        high=(178, 24, 43),
        fallback=fallback,
    )


def _scaled_color(
    *,
    value: float | None,
    scale: tuple[float, float] | None,
    low: tuple[int, int, int],
    high: tuple[int, int, int],
    fallback: str,
) -> str:
    if value is None or scale is None:
        return fallback
    low_value, high_value = scale
    if high_value <= low_value:
        ratio = 0.5
    else:
        ratio = min(1.0, max(0.0, (value - low_value) / (high_value - low_value)))
    rgb = tuple(
        round(low_part + (high_part - low_part) * ratio)
        for low_part, high_part in zip(low, high)
    )
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
