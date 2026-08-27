"""SQLite DDL and connection-configuration helpers for chemunited-sim recorder.

All CREATE TABLE and CREATE INDEX statements live here.  No simulation-domain
imports — this file must remain I/O-only so schema changes have a single
reason to touch it.
"""

from __future__ import annotations

import sqlite3

# ---------------------------------------------------------------------------
# Static tables (written once at Recorder construction)
# ---------------------------------------------------------------------------

SQL_CREATE_META = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT NOT NULL PRIMARY KEY,
    value TEXT NOT NULL
);
"""

SQL_CREATE_EDGE_CELLS = """
CREATE TABLE IF NOT EXISTS edge_cells (
    edge_id    TEXT    NOT NULL,
    cell_index INTEGER NOT NULL,
    position_m REAL    NOT NULL,
    length_m   REAL    NOT NULL,
    PRIMARY KEY (edge_id, cell_index)
);
"""

# ---------------------------------------------------------------------------
# Dynamic tables (appended every record interval)
# ---------------------------------------------------------------------------

SQL_CREATE_NODE_PRESSURE = """
CREATE TABLE IF NOT EXISTS node_pressure (
    time     REAL NOT NULL,
    node_id  TEXT NOT NULL,
    pressure REAL NOT NULL
);
"""
SQL_IDX_NODE_PRESSURE = (
    "CREATE INDEX IF NOT EXISTS idx_node_pressure_time ON node_pressure (time);"
)

SQL_CREATE_INVENTORY_STATE = """
CREATE TABLE IF NOT EXISTS inventory_state (
    time        REAL NOT NULL,
    node_id     TEXT NOT NULL,
    pressure    REAL NOT NULL,
    temperature REAL NOT NULL
);
"""
SQL_IDX_INVENTORY_STATE = (
    "CREATE INDEX IF NOT EXISTS idx_inventory_state_time ON inventory_state (time);"
)

SQL_CREATE_INVENTORY_CONTENT = """
CREATE TABLE IF NOT EXISTS inventory_content (
    time       REAL NOT NULL,
    node_id    TEXT NOT NULL,
    phase      TEXT NOT NULL,
    species_id TEXT NOT NULL,
    moles      REAL NOT NULL,
    volume     REAL NOT NULL
);
"""
SQL_IDX_INVENTORY_CONTENT = (
    "CREATE INDEX IF NOT EXISTS idx_inventory_content_time ON inventory_content (time);"
)

SQL_CREATE_EDGE_FLOW = """
CREATE TABLE IF NOT EXISTS edge_flow (
    time      REAL NOT NULL,
    edge_id   TEXT NOT NULL,
    flow_rate REAL NOT NULL
);
"""
SQL_IDX_EDGE_FLOW = "CREATE INDEX IF NOT EXISTS idx_edge_flow_time ON edge_flow (time);"

SQL_CREATE_CELL_STATE = """
CREATE TABLE IF NOT EXISTS cell_state (
    time           REAL    NOT NULL,
    edge_id        TEXT    NOT NULL,
    cell_index     INTEGER NOT NULL,
    phase          TEXT    NOT NULL,
    phase_fraction REAL    NOT NULL,
    temperature    REAL    NOT NULL
);
"""
SQL_IDX_CELL_STATE = (
    "CREATE INDEX IF NOT EXISTS idx_cell_state_time ON cell_state (time);"
)

SQL_CREATE_CELL_CONTENT = """
CREATE TABLE IF NOT EXISTS cell_content (
    time       REAL    NOT NULL,
    edge_id    TEXT    NOT NULL,
    cell_index INTEGER NOT NULL,
    phase      TEXT    NOT NULL,
    species_id TEXT    NOT NULL,
    moles      REAL    NOT NULL
);
"""
SQL_IDX_CELL_CONTENT = (
    "CREATE INDEX IF NOT EXISTS idx_cell_content_time ON cell_content (time);"
)

SQL_CREATE_COMPONENT_STATE = """
CREATE TABLE IF NOT EXISTS component_state (
    time      REAL NOT NULL,
    component TEXT NOT NULL,
    state     TEXT NOT NULL
);
"""
SQL_IDX_COMPONENT_STATE = (
    "CREATE INDEX IF NOT EXISTS idx_component_state_time ON component_state (time);"
)

# ---------------------------------------------------------------------------
# INSERT statements (used by Recorder.record via executemany)
# ---------------------------------------------------------------------------

SQL_INSERT_META = "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?);"
SQL_INSERT_EDGE_CELLS = (
    "INSERT INTO edge_cells "
    "(edge_id, cell_index, position_m, length_m) "
    "VALUES (?, ?, ?, ?);"
)
SQL_INSERT_NODE_PRESSURE = (
    "INSERT INTO node_pressure (time, node_id, pressure) VALUES (?, ?, ?);"
)
SQL_INSERT_INVENTORY_STATE = (
    "INSERT INTO inventory_state "
    "(time, node_id, pressure, temperature) "
    "VALUES (?, ?, ?, ?);"
)
SQL_INSERT_INVENTORY_CONTENT = (
    "INSERT INTO inventory_content "
    "(time, node_id, phase, species_id, moles, volume) "
    "VALUES (?, ?, ?, ?, ?, ?);"
)
SQL_INSERT_EDGE_FLOW = (
    "INSERT INTO edge_flow (time, edge_id, flow_rate) VALUES (?, ?, ?);"
)
SQL_INSERT_CELL_STATE = (
    "INSERT INTO cell_state "
    "(time, edge_id, cell_index, phase, phase_fraction, temperature) "
    "VALUES (?, ?, ?, ?, ?, ?);"
)
SQL_INSERT_CELL_CONTENT = (
    "INSERT INTO cell_content "
    "(time, edge_id, cell_index, phase, species_id, moles) "
    "VALUES (?, ?, ?, ?, ?, ?);"
)
SQL_INSERT_COMPONENT_STATE = (
    "INSERT INTO component_state (time, component, state) VALUES (?, ?, ?);"
)

# All DDL statements in creation order
_ALL_DDL = [
    SQL_CREATE_META,
    SQL_CREATE_EDGE_CELLS,
    SQL_CREATE_NODE_PRESSURE,
    SQL_IDX_NODE_PRESSURE,
    SQL_CREATE_INVENTORY_STATE,
    SQL_IDX_INVENTORY_STATE,
    SQL_CREATE_INVENTORY_CONTENT,
    SQL_IDX_INVENTORY_CONTENT,
    SQL_CREATE_EDGE_FLOW,
    SQL_IDX_EDGE_FLOW,
    SQL_CREATE_CELL_STATE,
    SQL_IDX_CELL_STATE,
    SQL_CREATE_CELL_CONTENT,
    SQL_IDX_CELL_CONTENT,
    SQL_CREATE_COMPONENT_STATE,
    SQL_IDX_COMPONENT_STATE,
]


def configure_connection(conn: sqlite3.Connection) -> None:
    """Apply WAL mode and performance PRAGMAs to *conn*.

    Must be called immediately after opening the connection and before any
    writes.  The GUI must open its own independent connection.
    """
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")


def create_all_tables(conn: sqlite3.Connection) -> None:
    """Execute all CREATE TABLE and CREATE INDEX statements."""
    for ddl in _ALL_DDL:
        conn.execute(ddl)
    conn.commit()
