"""Gas-liquid pressurized flow-through reactor — full chemunited-sim showcase.

Demonstrates every component type, gas/liquid phase transport, chemical
reactions, back-pressure regulation, mid-run valve switching, and SQLite
recording.

Platform overview
-----------------
A liquid reagent stream and a pressurised gas stream merge at a T-junction,
flow through a short plug-flow reactor tube, and enter a pressurised vessel
reactor.  Inside the reactor, reagent_a undergoes first-order decay to
product_b.  The reactor is held above the BPR setpoint by design:
upstream resistance (short 5 cm reactortube, D=2 mm) is kept lower than
downstream resistance (narrow 1.5 mm outlet lines), so the reactor pressure
settles well above the 2 bar setpoint.  Gas exits the BPR and is directed by
a two-position rotary valve to either a collection line or a waste line.
The liquid phase stays inside the reactor (batch liquid, continuous gas).

Network topology:

see full_platform_flow_diagram.svg

Components used
---------------
  PressureControlData   gassupply, productsink, wastesink               (3)
  FlowSourceData        liquidpump                                       (1)
  PlugFlowComponentData gastube, liquidtube, reactortube, outlettube,
                        collecttube, wastetube                          (6)
  VesselComponentData   reactor  (top_access=1, bottom_access=1)         (1)
  BackPressureRegulatorData  bpr                                         (1)
  JunctionData          tmixer  (3 external ports)                       (1)
  ValveComponentData    divertvalve  (2-position rotary selector)        (1)

Chemistry
---------
  reagent_a -> product_b   first-order k = 0.05 /s   liquid phase

Simulation timeline
-------------------
  t =  0 s  start; valve in COLLECT position (port 0 <-> port 1 open)
  t = 20 s  valve rotates to WASTE position  (port 0 <-> port 2 open)
  t = 60 s  end; recorder closed; results printed

Transport note
--------------
The rotary valve centre port (port 0) is patched to is_hub=True after graph
compilation.  This lets the transport engine's hub-merge routine route pockets
arriving via the upstream TRANSPORT edge through the open JUNCTION channel
inside the valve and into the correct downstream TRANSPORT edge.  Without this
patch, pockets would be silently discarded at the valve centre node.

All quantities are in SI units (Pa, m3, m, s, mol, K).
"""

from __future__ import annotations

import pathlib
import sqlite3
from datetime import datetime

from chemunited_core.common.constant import ATMOSPHERE_PRESSURE_PA
from chemunited_core.common.enums import ConnectionType, PhaseKind
from chemunited_core.components import (
    BackPressureRegulatorData,
    BackPressureRegulatorMode,
    FlowSourceData,
    FlowSourceMode,
    JunctionData,
    JunctionMode,
    PlugFlowComponentData,
    PlugFlowMode,
    PressureControlData,
    PressureControlMode,
    ValveComponentData,
    ValveMode,
    VesselComponentData,
    VesselMode,
)
from chemunited_core.components.valve import rotate_rotor
from chemunited_core.compounds import COMPOUNDS, ChemicalEntity, VolumeContentBase
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_core.utils.internal_quantity import ChemUnitQuantity

from chemunited_sim.adapter import HydraulicNode, compile_graph
from chemunited_sim.reactions import FirstOrderDecay
from chemunited_sim.recorder import Recorder
from chemunited_sim.visualization import load_latest_snapshot, render_pyvis_html
from chemunited_sim.worker import SimConfig, Worker

# ---------------------------------------------------------------------------
# Section 1 — Chemical compound registry
# ---------------------------------------------------------------------------
COMPOUNDS.clear()  # remove any leftovers from a previous run in this interpreter

COMPOUNDS.register(
    ChemicalEntity(
        name="reagent_a",
        molecular_weight=120.0,  # g/mol
        cp_liquid=150.0,  # J/(mol*K)
        density_liquid=1050.0,  # kg/m3
    )
)
COMPOUNDS.register(
    ChemicalEntity(
        name="product_b",
        molecular_weight=120.0,
        cp_liquid=150.0,
        density_liquid=1020.0,
    )
)
COMPOUNDS.register(
    ChemicalEntity(
        name="solvent",
        molecular_weight=78.0,
        cp_liquid=130.0,
        density_liquid=880.0,
    )
)
COMPOUNDS.register(
    ChemicalEntity(
        name="nitrogen",
        molecular_weight=28.0,
        cp_gas=29.0,
    )
)

print("=== chemunited-sim Full Platform Example ===\n")
print("Compounds registered:", COMPOUNDS.names)


# ---------------------------------------------------------------------------
# Section 2 — Component construction
# ---------------------------------------------------------------------------
# Component name rules: no dots, no underscores, no spaces.

# Pressure / flow boundary components
gassupply = PressureControlData.from_mode(
    PressureControlMode(name="gassupply", setpoint=ChemUnitQuantity("3 bar"))
)
liquidpump = FlowSourceData.from_mode(
    FlowSourceMode(name="liquidpump", flow_rate=ChemUnitQuantity("3 ml/min"))
)
productsink = PressureControlData.from_mode(
    PressureControlMode(name="productsink", setpoint=ChemUnitQuantity("1 bar"))
)
wastesink = PressureControlData.from_mode(
    PressureControlMode(name="wastesink", setpoint=ChemUnitQuantity("1 bar"))
)
# Plug-flow tube segments
gastube = PlugFlowComponentData.from_mode(
    PlugFlowMode(
        name="gastube",
        length=ChemUnitQuantity("10 cm"),
        diameter=ChemUnitQuantity("1.5 mm"),
    )
)
liquidtube = PlugFlowComponentData.from_mode(
    PlugFlowMode(
        name="liquidtube",
        length=ChemUnitQuantity("10 cm"),
        diameter=ChemUnitQuantity("1.5 mm"),
    )
)
reactortube = PlugFlowComponentData.from_mode(
    PlugFlowMode(
        name="reactortube",
        length=ChemUnitQuantity("5 cm"),
        diameter=ChemUnitQuantity("2 mm"),
    )
)
outlettube = PlugFlowComponentData.from_mode(
    PlugFlowMode(
        name="outlettube",
        length=ChemUnitQuantity("20 cm"),
        diameter=ChemUnitQuantity("1.5 mm"),
    )
)
collecttube = PlugFlowComponentData.from_mode(
    PlugFlowMode(
        name="collecttube",
        length=ChemUnitQuantity("10 cm"),
        diameter=ChemUnitQuantity("1.5 mm"),
    )
)
wastetube = PlugFlowComponentData.from_mode(
    PlugFlowMode(
        name="wastetube",
        length=ChemUnitQuantity("10 cm"),
        diameter=ChemUnitQuantity("1.5 mm"),
    )
)

# T-junction mixer: 3 external ports (1 = gas in, 2 = liquid in, 3 = out)
tmixer = JunctionData.from_mode(JunctionMode(name="tmixer", number_ports=3))

# Reactor vessel: 10 mL
# Port numbering from vessel.internal_structure (top_access=1, bottom_access=1):
#   port 1 -> TOP     gas outlet  -> bpr
#   port 2 -> BOTTOM  mixed inlet <- reactortube
#   port 3 -> HEAT    (filtered by adapter, not in hydraulic graph)
# No liquid outlet — liquid stays inside (batch liquid, continuous gas).
reactor = VesselComponentData.from_mode(
    VesselMode(
        name="reactor",
        capacity=ChemUnitQuantity("10 ml"),
        top_access=1,
        bottom_access=1,
    )
)

# Back-pressure regulator: holds the reactor headspace at >= 2 bar
bpr = BackPressureRegulatorData.from_mode(
    BackPressureRegulatorMode(name="bpr", setpoint=ChemUnitQuantity("2 bar"))
)

# Two-position rotary divert valve
# Stator layout: outer ring holds ports 1 and 2; inner ring (centre) = port 0
# Rotor layout : channel 7 spans outer-ring position 0 to the centre
#   Default -> port 0 <-> port 1 open (collect path active)
#   After 1 CW step -> port 0 <-> port 2 open (waste path active)
divertvalve = ValveComponentData.from_mode(
    ValveMode(
        name="divertvalve",
        stator_ports=[(1, 2), (0,)],
        rotor_ports=[(7, None), (7,)],
    )
)


# ---------------------------------------------------------------------------
# Section 3 — Initial reactor inventory
# ---------------------------------------------------------------------------
# Overwrite the default (all-gas, empty-liquid) InventoryNode so the reactor
# starts with a liquid charge.  compile_graph() deep-copies the InventoryNode,
# so these values are decoupled from the component after compilation.

_OPERATING_P = 2.0 * ATMOSPHERE_PRESSURE_PA  # ~2.03e5 Pa — matches BPR setpoint

reactor.internal_inventory.liq_content = VolumeContentBase(
    phase_kind=PhaseKind.LIQUID,
    volume=3.0e-6,  # 3 mL
    initial_species={
        "reagent_a": 1.0e-4,  # 0.1 mmol
        "solvent": 3.4e-2,  # 34 mmol (~fills 3 mL at 880 kg/m3)
    },
    initial_pressure=_OPERATING_P,
    initial_temperature=298.15,
)
reactor.internal_inventory.gas_content = VolumeContentBase(
    phase_kind=PhaseKind.GAS,
    volume=7.0e-6,  # 7 mL headspace
    initial_species={"nitrogen": 4.3e-1},  # mol at 1.5 bar, 298 K, 7 mL
    initial_pressure=_OPERATING_P,
    initial_temperature=298.15,
)

liq_content = reactor.internal_inventory.liq_content
gas_content = reactor.internal_inventory.gas_content
print(
    f"\nReactor initial inventory:"
    f"\n  Liquid {liq_content.volume*1e6:.1f} mL  "
    f"reagent_a={liq_content.initial_species['reagent_a']:.2e} mol"
    f"\n  Gas    {gas_content.volume*1e6:.1f} mL  "
    f"nitrogen={gas_content.initial_species['nitrogen']:.3f} mol"
)


# ---------------------------------------------------------------------------
# Section 4 — External edges (physical tubing connections)
# ---------------------------------------------------------------------------
_D_SMALL = ChemUnitQuantity("1.5 mm")  # narrow inlet lines
_D_MAIN = ChemUnitQuantity("2 mm")  # main network lines
_L_STUB = ChemUnitQuantity("2 cm")  # short connector stub

edges = [
    # -- gas supply path --
    EdgeData.from_mode(
        EdgeMode(
            name="egsgt",
            origin="gassupply",
            origin_port=1,
            destination="gastube",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=_L_STUB,
            diameter=_D_SMALL,
        )
    ),
    EdgeData.from_mode(
        EdgeMode(
            name="egtmixer",
            origin="gastube",
            origin_port=2,
            destination="tmixer",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=_L_STUB,
            diameter=_D_SMALL,
        )
    ),
    # -- liquid pump path --
    EdgeData.from_mode(
        EdgeMode(
            name="elplt",
            origin="liquidpump",
            origin_port=1,
            destination="liquidtube",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=_L_STUB,
            diameter=_D_SMALL,
        )
    ),
    EdgeData.from_mode(
        EdgeMode(
            name="eltmixer",
            origin="liquidtube",
            origin_port=2,
            destination="tmixer",
            destination_port=2,
            classification=ConnectionType.HYDRAULIC,
            length=_L_STUB,
            diameter=_D_SMALL,
        )
    ),
    # -- mixer to reactor --
    EdgeData.from_mode(
        EdgeMode(
            name="emixerrt",
            origin="tmixer",
            origin_port=3,
            destination="reactortube",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=_L_STUB,
            diameter=_D_MAIN,
        )
    ),
    EdgeData.from_mode(
        EdgeMode(
            name="ertrx",
            origin="reactortube",
            origin_port=2,
            destination="reactor",
            destination_port=2,  # BOTTOM port 2 (mixed inlet)
            classification=ConnectionType.HYDRAULIC,
            length=_L_STUB,
            diameter=_D_MAIN,
        )
    ),
    # -- gas outlet through BPR (TOP port 1) --
    # Narrow lines keep P_reactor above setpoint.
    EdgeData.from_mode(
        EdgeMode(
            name="erxbpr",
            origin="reactor",
            origin_port=1,  # TOP port 1 (gas outlet)
            destination="bpr",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=_L_STUB,
            diameter=_D_SMALL,
        )
    ),
    EdgeData.from_mode(
        EdgeMode(
            name="ebprot",
            origin="bpr",
            origin_port=2,
            destination="outlettube",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=_L_STUB,
            diameter=_D_SMALL,
        )
    ),
    # -- divert valve --
    EdgeData.from_mode(
        EdgeMode(
            name="eotvalve",
            origin="outlettube",
            origin_port=2,
            destination="divertvalve",
            destination_port=0,  # valve CENTRE port
            classification=ConnectionType.HYDRAULIC,
            length=_L_STUB,
            diameter=_D_SMALL,
        )
    ),
    # collect path (default active: valve port 0 <-> port 1)
    EdgeData.from_mode(
        EdgeMode(
            name="evalvect",
            origin="divertvalve",
            origin_port=1,
            destination="collecttube",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=_L_STUB,
            diameter=_D_SMALL,
        )
    ),
    EdgeData.from_mode(
        EdgeMode(
            name="ectproduct",
            origin="collecttube",
            origin_port=2,
            destination="productsink",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=_L_STUB,
            diameter=_D_SMALL,
        )
    ),
    # waste path (active after one CW rotation: valve port 0 <-> port 2)
    EdgeData.from_mode(
        EdgeMode(
            name="evalvewt",
            origin="divertvalve",
            origin_port=2,
            destination="wastetube",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=_L_STUB,
            diameter=_D_SMALL,
        )
    ),
    EdgeData.from_mode(
        EdgeMode(
            name="ewtsink",
            origin="wastetube",
            origin_port=2,
            destination="wastesink",
            destination_port=1,
            classification=ConnectionType.HYDRAULIC,
            length=_L_STUB,
            diameter=_D_SMALL,
        )
    ),
]

components = [
    gassupply,
    liquidpump,
    productsink,
    wastesink,
    gastube,
    liquidtube,
    reactortube,
    outlettube,
    collecttube,
    wastetube,
    tmixer,
    reactor,
    bpr,
    divertvalve,
]

print(f"\nComponents : {len(components)}")
print(f"Edges      : {len(edges)}")


# ---------------------------------------------------------------------------
# Section 5 — Compile graph + hub patch for valve centre
# ---------------------------------------------------------------------------
graph = compile_graph(components, edges)

# Hub patch
# ---------
# The transport engine routes arriving pockets through JUNCTION edges toward
# either an inventory node or a *hub* node (HydraulicNode.is_hub=True).
# A valve centre port is not marked as a hub by the standard compiler, so
# pockets arriving at divertvalve.0 from eotvalve would be discarded.
# Replacing the frozen node object with is_hub=True activates the hub-merge
# routine (_process_hub), which distributes merged pockets to the downstream
# TRANSPORT edge whose valve channel is currently open.
_old = graph.nodes["divertvalve.0"]
graph.nodes["divertvalve.0"] = HydraulicNode(
    node_id=_old.node_id,
    boundary=_old.boundary,
    is_hub=True,
    component=_old.component,
)

print(
    f"\nHydraulic graph : {len(graph.nodes)} nodes, {len(graph.edges)} edges"
    f"\nBPR edges       : {graph.bpr_edges}"
    f"\nInventory nodes : {list(graph.inventory_nodes)}"
)


# ---------------------------------------------------------------------------
# Section 6 — Reaction model
# ---------------------------------------------------------------------------
reaction = FirstOrderDecay(
    reactant="reagent_a",
    product="product_b",
    rate_constant=0.05,  # 1/s
    phase=PhaseKind.LIQUID,
    delta_temperature_per_mol_converted=2.0,  # K/mol (mild exotherm)
)

reactions_map = {"reactor.Inventory": [reaction]}


# ---------------------------------------------------------------------------
# Section 7 — Recorder
# ---------------------------------------------------------------------------
_sim_dir = pathlib.Path(__file__).parent / "simulation"
_sim_dir.mkdir(exist_ok=True)

_ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
db_path = _sim_dir / f"fullplatform_{_ts}.db"

recorder = Recorder(
    db_path=db_path,
    graph=graph,
    dt=0.1,
    record_interval=2.0,
    platform_name="full_platform_example",
)

print(f"\nRecording to: {db_path.name}")


# ---------------------------------------------------------------------------
# Valve sync helper
# ---------------------------------------------------------------------------


def _sync_valve_to_graph(valve: ValveComponentData) -> None:
    """Propagate valve InternalEdge.resistance_override to HydraulicGraph.

    Call after every valve rotation + sync_internal_state() so the solver
    uses the updated open/closed resistances on the next step.
    """
    for (origin, dest), ie in valve.internal_edges.items():
        eid = f"{valve.name}.{origin}.{dest}"
        if eid in graph.edges:
            graph.edges[eid].resistance_override = ie.resistance_override


# ---------------------------------------------------------------------------
# Section 8 — Simulation loop
# ---------------------------------------------------------------------------
cfg = SimConfig(dt=0.1, t_end=60.0)

worker = Worker(
    graph=graph,
    components=components,
    config=cfg,
    reactions_map=reactions_map,
    recorder=recorder,
)

T_VALVE_SWITCH = 20.0  # time to rotate the valve (seconds)
valve_switched = False

print(f"\n{'-'*58}")
print(f" Running:  dt={cfg.dt} s,  t_end={cfg.t_end} s")
print(" Valve starts in COLLECT position (port 0 <-> port 1)")
print(f"{'-'*58}")

_REPORT_AT = {10.0, 20.0, 30.0, 40.0, 50.0, 60.0}

while round(worker.t / cfg.dt) <= round(cfg.t_end / cfg.dt):

    # Switch valve at T_VALVE_SWITCH
    if not valve_switched and worker.t >= T_VALVE_SWITCH - cfg.dt * 0.5:
        divertvalve.rotor_ports = rotate_rotor(divertvalve.rotor_ports, clockwise=True)
        divertvalve.sync_internal_state()
        _sync_valve_to_graph(divertvalve)
        valve_switched = True

        active = [
            f"{o}<->{d}"
            for (o, d), ie in divertvalve.internal_edges.items()
            if ie.resistance_override is None
        ]
        print(f"\n  *** t={worker.t:.1f}s  Valve -> WASTE  (active: {active}) ***\n")

    worker.step()

    # Periodic progress report
    t_now = round(worker.t / cfg.dt) * cfg.dt
    if any(abs(t_now - tr) < cfg.dt * 0.5 for tr in _REPORT_AT):
        inv = worker.inv_states.get("reactor.Inventory")
        if inv is not None:
            n_a = inv.liq_species_moles.get("reagent_a", 0.0)
            n_b = inv.liq_species_moles.get("product_b", 0.0)
            p_b = inv.pressure / ATMOSPHERE_PRESSURE_PA
            frac = inv.liq_volume / max(inv.liq_volume + inv.gas_volume, 1e-30) * 100
            print(
                f"  t={worker.t:5.1f}s  P={p_b:.3f}bar  T={inv.temperature:.2f}K"
                f"  liq={frac:.1f}%  A={n_a:.3e}mol  B={n_b:.3e}mol"
            )

# Close recorder (Worker.step() does not close it; only Worker.run() does)
recorder.close()

print(f"\n{'-'*58}")
print(" Simulation complete")
print(f"{'-'*58}")


# ---------------------------------------------------------------------------
# Section 9 — Post-run analysis
# ---------------------------------------------------------------------------

# Reaction conversion in reactor
inv = worker.inv_states["reactor.Inventory"]
n_a_init = 1.0e-4
n_a_final = inv.liq_species_moles.get("reagent_a", 0.0)
n_b_final = inv.liq_species_moles.get("product_b", 0.0)
conv_pct = (n_a_init - n_a_final) / n_a_init * 100 if n_a_init > 0 else 0.0

print("\n-- Reactor final inventory --")
print(f"  Pressure   : {inv.pressure / ATMOSPHERE_PRESSURE_PA:.4f} bar")
print(f"  Temperature: {inv.temperature:.3f} K")
print(f"  Liq volume : {inv.liq_volume*1e6:.3f} mL")
print(f"  Gas volume : {inv.gas_volume*1e6:.3f} mL")
print(f"  reagent_a  : {n_a_final:.4e} mol  (init {n_a_init:.4e})")
print(f"  product_b  : {n_b_final:.4e} mol")
print(f"  Conversion : {conv_pct:.1f} %")

# Key nodal pressures
hyd = worker.hyd_state
if hyd is not None:
    print("\n-- Key pressures (bar) --")
    key_nodes = [
        "gassupply.1",
        "tmixer.0",
        "reactor.Inventory",
        "bpr.1",
        "bpr.2",
        "divertvalve.0",
        "divertvalve.1",
        "divertvalve.2",
        "productsink.1",
        "wastesink.1",
    ]
    for nid in key_nodes:
        p = hyd.pressures.get(nid)
        if p is not None:
            print(f"  {nid:<26s}: {p / ATMOSPHERE_PRESSURE_PA:.4f} bar")

# Transport queue snapshot
print("\n-- Transport queue lengths --")
key_edges = [
    "gastube.1.2",
    "reactortube.1.2",
    "ertrx",
    "erxbpr",
    "outlettube.1.2",
    "eotvalve",
    "evalvect",
    "evalvewt",
    "collecttube.1.2",
    "wastetube.1.2",
]
ts = worker.transport_state
for eid in key_edges:
    q = ts.edge_queues.get(eid)
    if q is not None:
        phases = [p.phase_kind.value[0].upper() for p in q]
        summary = ", ".join(phases[:8]) + ("..." if len(phases) > 8 else "")
        print(f"  {eid:<28s}: {len(q):3d} pockets  [{summary}]")

# Flow rates
if hyd is not None:
    print("\n-- Flow rates (nL/s, last step) --")
    for eid in key_edges:
        q_flow = hyd.flows.get(eid)
        if q_flow is not None:
            print(f"  {eid:<28s}: {q_flow*1e9:+.3f} nL/s")

# SQLite summary
print(f"\n-- SQLite: {db_path.name} --")
conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
try:
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    print(f"  Tables: {tables}")
    for tname in tables:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {tname}").fetchone()[0]
        print(f"  {tname:<22s}: {cnt:>6d} rows")

    times = [
        r[0]
        for r in conn.execute("SELECT DISTINCT time FROM node_pressure ORDER BY time")
    ]
    print(f"\n  Recorded time-points ({len(times)}): {[f'{t:.0f}s' for t in times]}")

    print("\n  reagent_a decay in reactor (from inventory_content):")
    rows = conn.execute("""
        SELECT time, moles FROM inventory_content
        WHERE  node_id = 'reactor.Inventory'
          AND  phase   = 'liquid'
          AND  species_id = 'reagent_a'
        ORDER  BY time
        """).fetchall()
    for t_rec, moles in rows:
        bar = "#" * max(1, int(moles / n_a_init * 30))
        print(f"    t={t_rec:5.1f}s  {moles:.4e} mol  {bar}")
finally:
    conn.close()

print(f"\n{'='*58}")
print(" Example finished successfully.")
print(f"{'='*58}")


html_path = _sim_dir / f"fullplatform_{_ts}.html"
snapshot = load_latest_snapshot(db_path)
html_path.write_text(
    render_pyvis_html(graph=graph, components=components, snapshot=snapshot),
    encoding="utf-8",
)

print("\n-- Pyvis HTML export --")
print(f"  Wrote: {html_path}")
print("  Hover nodes/edges to inspect the latest recorded pressures and flows.")
