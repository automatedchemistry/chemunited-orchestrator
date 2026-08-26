"""Recorder writer — the sole SQLite writer in chemunited-sim.

``Recorder`` opens one connection at construction, keeps it alive for the
entire simulation run, and writes all dynamic tables atomically each record
interval.

Do NOT write to SQLite from any other module.  See CLAUDE.md.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

from chemunited_core.common.enums import PhaseKind
from chemunited_core.components import ComponentData
from chemunited_core.figure_registry import SolenoidValve2WayData, SolenoidValveData
from chemunited_core.figure_registry.rotary_valve import RotaryValveData
from loguru import logger

from ..adapter.models import HydraulicGraph
from ..common.constant import RECORDER_CELL_LENGTH_M, RECORDER_INTERVAL_DEFAULT
from ..hydraulics.models import HydraulicState
from ..inventory.models import InventoryState
from ..transport.models import Pocket, TransportState
from .cells import build_cell_definitions
from .models import CellDefinition
from .schema import (
    SQL_INSERT_CELL_CONTENT,
    SQL_INSERT_CELL_STATE,
    SQL_INSERT_COMPONENT_STATE,
    SQL_INSERT_EDGE_CELLS,
    SQL_INSERT_EDGE_FLOW,
    SQL_INSERT_INVENTORY_CONTENT,
    SQL_INSERT_INVENTORY_STATE,
    SQL_INSERT_META,
    SQL_INSERT_NODE_PRESSURE,
    configure_connection,
    create_all_tables,
)

# Sentinel species_id written when a phase has no tracked species, so the
# GUI always finds a row for every (node_id, phase) pair.
_CARRIER_SPECIES_ID = "__carrier__"


class RecorderWriteError(RuntimeError):
    """Raised when a SQLite write fails mid-record.

    The original :class:`sqlite3.Error` is chained as ``__cause__``.
    """


class Recorder:
    """Writes simulation state to a SQLite database at fixed record intervals.

    Opens a single WAL-mode connection on construction and keeps it alive for
    the entire simulation run.  All dynamic tables are written atomically
    in a single transaction per record step via ``executemany``.

    **Thread safety**: the connection is single-threaded (``check_same_thread
    = True``).  The sim worker is the sole writer.  GUI readers must open an
    independent read-only connection.

    **Directory**: the parent directory of *db_path* must exist before
    construction.  ``Recorder`` does not create directories.

    Parameters
    ----------
    db_path:
        Path to the SQLite file to create (overwritten if it already exists).
    graph:
        Compiled hydraulic graph.  Used to build cell definitions and written
        to the static ``edge_cells`` table at construction.
    dt:
        Simulation time step in seconds.
    record_interval:
        How often (in simulation seconds) to write a snapshot.
        Must be a positive multiple of *dt*.  A warning is logged if it is not
        an exact multiple.
    platform_name:
        Human-readable platform identifier stored in the ``meta`` table.
    cell_length_m:
        Nominal cell length for edge slicing.  Defaults to
        :data:`~chemunited_sim.common.constant.RECORDER_CELL_LENGTH_M`.
    components:
        Live component data, keyed by component name.  Used to capture
        discrete component state (rotary valve rotor position, solenoid
        valve open/closed) into the ``component_state`` table each record
        step.  Optional — omit for graphs with no such components, or when
        discrete-state recording isn't needed.
    """

    def __init__(
        self,
        db_path: str | os.PathLike,
        graph: HydraulicGraph,
        dt: float,
        record_interval: float = RECORDER_INTERVAL_DEFAULT,
        platform_name: str = "",
        cell_length_m: float = RECORDER_CELL_LENGTH_M,
        components: dict[str, ComponentData] | None = None,
    ) -> None:
        self._graph = graph
        self._dt = dt
        self._record_interval = record_interval
        self._components: dict[str, ComponentData] = components or {}

        # Integer-tick interval — pre-computed to avoid per-step float division
        raw_ticks = record_interval / dt
        self._interval_ticks: int = round(raw_ticks)
        if abs(raw_ticks - self._interval_ticks) > 0.01:
            logger.warning(
                "Recorder: record_interval={} is not an exact multiple of dt={}. "
                "Actual interval rounded to {:.6f} s.",
                record_interval,
                dt,
                self._interval_ticks * dt,
            )

        # Build cell definitions (once)
        self._cell_defs: list[CellDefinition] = build_cell_definitions(
            graph, cell_length_m
        )
        # Pre-build per-edge cell list for fast lookup
        self._cells_by_edge: dict[str, list[CellDefinition]] = defaultdict(list)
        for cd in self._cell_defs:
            self._cells_by_edge[cd.edge_id].append(cd)

        # Pre-compute cross-section areas for cell projection
        self._edge_area: dict[str, float] = {
            eid: math.pi * (edge.diameter / 2.0) ** 2
            for eid, edge in graph.edges.items()
            if edge.diameter > 0.0
        }

        # Open connection (overwrite existing file)
        db_path = os.fspath(db_path)
        if os.path.exists(db_path):
            os.remove(db_path)
        self._conn: sqlite3.Connection | None = sqlite3.connect(db_path)
        configure_connection(self._conn)
        create_all_tables(self._conn)

        # Write static tables
        timestamp = datetime.now(tz=timezone.utc).isoformat()
        meta_rows = [
            ("dt", str(dt)),
            ("record_interval", str(record_interval)),
            ("platform_name", platform_name),
            ("timestamp", timestamp),
        ]
        cell_rows = [
            (cd.edge_id, cd.cell_index, cd.position_m, cd.length_m)
            for cd in self._cell_defs
        ]
        with self._conn:
            self._conn.executemany(SQL_INSERT_META, meta_rows)
            self._conn.executemany(SQL_INSERT_EDGE_CELLS, cell_rows)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def should_record(self, t: float) -> bool:
        """Return ``True`` if a snapshot should be written at simulation time *t*.

        Uses integer-tick arithmetic to avoid floating-point modulo drift::

            tick = round(t / dt)
            should_record = (tick % interval_ticks) == 0
        """
        tick = round(t / self._dt)
        return (tick % self._interval_ticks) == 0

    def record(
        self,
        t: float,
        hyd_state: HydraulicState,
        transport_state: TransportState,
        inv_states: dict[str, InventoryState],
    ) -> None:
        """Write a snapshot of all dynamic tables at simulation time *t*.

        If ``should_record(t)`` is ``False`` the call is a no-op.

        All tables are written in one atomic transaction.  On failure a
        :class:`RecorderWriteError` is raised; no partial snapshot is
        committed.

        Parameters
        ----------
        t:
            Current simulation time in seconds.
        hyd_state:
            Hydraulic solve result for this step.
        transport_state:
            FIFO pocket queues for all transport edges.
        inv_states:
            All live inventory states, keyed by ``inv_node_id``.
        """
        if not self.should_record(t):
            return
        if self._conn is None:
            raise RecorderWriteError("Recorder.record called after close().")

        node_pressure_rows: list[tuple] = []
        inv_state_rows: list[tuple] = []
        inv_content_rows: list[tuple] = []
        edge_flow_rows: list[tuple] = []
        cell_state_rows: list[tuple] = []
        cell_content_rows: list[tuple] = []
        component_state_rows: list[tuple] = []

        # node_pressure
        for node_id, pressure in hyd_state.pressures.items():
            node_pressure_rows.append((t, node_id, pressure))

        # edge_flow
        for edge_id, flow_rate in hyd_state.flows.items():
            edge_flow_rows.append((t, edge_id, flow_rate))

        # inventory tables
        for node_id, state in inv_states.items():
            inv_state_rows.append((t, node_id, state.pressure, state.temperature))
            inv_content_rows.extend(
                _inventory_content_rows(
                    t,
                    node_id,
                    "liquid",
                    state.liq_species_moles,
                    state.liq_volume,
                )
            )
            inv_content_rows.extend(
                _inventory_content_rows(
                    t,
                    node_id,
                    "gas",
                    state.gas_species_moles,
                    state.gas_volume,
                )
            )

        # cell tables — project pockets onto fixed cells
        for edge_id, cell_list in self._cells_by_edge.items():
            queue = transport_state.edge_queues.get(edge_id)
            if not queue:
                continue
            area = self._edge_area.get(edge_id)
            if area is None or area <= 0.0:
                continue

            # Build pocket intervals: (start_m, end_m, Pocket) from origin end
            pocket_intervals: list[tuple[float, float, Pocket]] = []
            cursor = 0.0
            for pocket in reversed(
                queue
            ):  # deque[-1] = origin end → reversed = origin first
                pocket_len = pocket.volume / area
                pocket_intervals.append((cursor, cursor + pocket_len, pocket))
                cursor += pocket_len

            for cell_def in cell_list:
                c_start = cell_def.position_m
                c_end = c_start + cell_def.length_m
                cell_vol = cell_def.length_m * area

                # Accumulate per phase
                phase_vol: dict[PhaseKind, float] = {}
                phase_vol_temp: dict[PhaseKind, float] = {}
                phase_species: dict[PhaseKind, dict[str, float]] = {}

                for p_start, p_end, pocket in pocket_intervals:
                    if p_end <= c_start:
                        continue
                    if p_start >= c_end:
                        break  # intervals are sorted; no more overlaps
                    overlap_len = min(p_end, c_end) - max(p_start, c_start)
                    overlap_vol = overlap_len * area
                    ph = pocket.phase_kind

                    phase_vol[ph] = phase_vol.get(ph, 0.0) + overlap_vol
                    phase_vol_temp[ph] = (
                        phase_vol_temp.get(ph, 0.0) + overlap_vol * pocket.temperature
                    )
                    if pocket.species_moles:
                        sp_dict = phase_species.setdefault(ph, {})
                        frac = overlap_vol / pocket.volume if pocket.volume > 0 else 0.0
                        for sp, mol in pocket.species_moles.items():
                            sp_dict[sp] = sp_dict.get(sp, 0.0) + mol * frac

                for ph, vol in phase_vol.items():
                    if vol <= 0.0:
                        continue
                    phase_str = ph.name.lower()
                    phase_fraction = vol / cell_vol
                    temperature = phase_vol_temp[ph] / vol
                    cell_state_rows.append(
                        (
                            t,
                            edge_id,
                            cell_def.cell_index,
                            phase_str,
                            phase_fraction,
                            temperature,
                        )
                    )
                    sp_dict = phase_species.get(ph, {})
                    for sp, mol in sp_dict.items():
                        cell_content_rows.append(
                            (
                                t,
                                edge_id,
                                cell_def.cell_index,
                                phase_str,
                                sp,
                                mol,
                            )
                        )

        # component_state — discrete state not otherwise recoverable from the
        # continuous tables above (rotor position, solenoid open/closed)
        for name, component in self._components.items():
            if isinstance(component, RotaryValveData):
                component_state: dict[str, object] = {
                    "rotor_ports": component.rotor_ports
                }
            elif isinstance(component, (SolenoidValveData, SolenoidValve2WayData)):
                component_state = {"opened": component.opened}
            else:
                continue
            component_state_rows.append((t, name, json.dumps(component_state)))

        try:
            with self._conn:
                self._conn.executemany(SQL_INSERT_NODE_PRESSURE, node_pressure_rows)
                self._conn.executemany(SQL_INSERT_INVENTORY_STATE, inv_state_rows)
                self._conn.executemany(SQL_INSERT_INVENTORY_CONTENT, inv_content_rows)
                self._conn.executemany(SQL_INSERT_EDGE_FLOW, edge_flow_rows)
                self._conn.executemany(SQL_INSERT_CELL_STATE, cell_state_rows)
                self._conn.executemany(SQL_INSERT_CELL_CONTENT, cell_content_rows)
                self._conn.executemany(SQL_INSERT_COMPONENT_STATE, component_state_rows)
        except sqlite3.Error as exc:
            raise RecorderWriteError(
                f"Recorder failed to write at t={t:.6f} s: {exc}"
            ) from exc

    def close(self) -> None:
        """Flush pending writes and close the database connection.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        if self._conn is not None:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _inventory_content_rows(
    t: float,
    node_id: str,
    phase_str: str,
    species_moles: dict[str, float],
    volume: float,
) -> list[tuple]:
    """Build ``inventory_content`` rows for one phase.

    Always emits at least one row so the GUI can read the phase volume even
    when no chemical species are tracked.  Empty-species phases get a
    sentinel row with ``species_id = '__carrier__'`` and ``moles = 0.0``.
    """
    if species_moles:
        return [
            (t, node_id, phase_str, sp, mol, volume)
            for sp, mol in species_moles.items()
        ]
    return [(t, node_id, phase_str, _CARRIER_SPECIES_ID, 0.0, volume)]
