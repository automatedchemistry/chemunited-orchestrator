"""Platform setup: gas-liquid pressurised flow-through reactor."""


def build_draw(platform) -> None:
    # ── Chemistry ──────────────────────────────────────────────────────────────
    platform.add_compound(
        name="reagent_a", molecular_weight=120.0, cp_liquid=150.0, density_liquid=1050.0
    )
    platform.add_compound(
        name="product_b", molecular_weight=120.0, cp_liquid=150.0, density_liquid=1020.0
    )
    platform.add_compound(
        name="solvent", molecular_weight=78.0, cp_liquid=130.0, density_liquid=880.0
    )
    platform.add_compound(name="nitrogen", molecular_weight=28.0, cp_gas=29.0)

    # ── Components ─────────────────────────────────────────────────────────────
    platform.add_component(name="gassupply", figure="Source", setpoint="1.3 bar")
    platform.add_component(
        name="liquidpump",
        figure="SyringePump",
        syringe_volume="5000 ml",
        syringe_actual_volume="5000 ml",
    )
    platform.add_component(
        name="liquidrecicly",
        figure="GlassBottle",
        capacity="10 ml",
        heat_exchange=True,
        surface_temperature="315 K",
    )
    platform.add_component(name="pump", figure="HPLCPump")
    platform.add_component(name="productsink", figure="Sink")
    platform.add_component(name="wastesink", figure="Sink")
    platform.add_component(
        name="reactortube", figure="FlowReactor", length="5 cm", diameter="2 mm"
    )
    platform.add_component(name="tmixer", figure="Distributor", number_ports=4)
    platform.add_component(
        name="reactor",
        figure="GlassBottle",
        capacity="10 ml",
        top_access=1,
        bottom_access=2,
        pressure_access=True,
        heat_exchange=True,
        surface_temperature="315 K",
        heat_transfer_coefficient="100 W/(m^2*K)",
    )
    platform.add_component(
        name="bpr", figure="BackPressureRegulator", setpoint="1.2 bar"
    )
    platform.add_component(name="divertvalve", figure="SolenoidValve2Way")
    platform.add_component(name="mfc", figure="MFCComponent")
    platform.add_component(name="chiller", figure="TemperatureControl")

    platform.fill_iventory(
        "reactor",
        "Inventory",
        "liq",
        {
            "volume": 3.0e-6,
            "initial_species": {"reagent_a": 1.0e-4, "solvent": 3.4e-2},
            "initial_pressure": 202650.0,
        },
    )

    platform.fill_iventory(
        "reactor",
        "Inventory",
        "gas",
        {
            "volume": 7.0e-6,
            "initial_species": {"nitrogen": 4.3e-1},
            "initial_pressure": 202650.0,
        },
    )

    platform.fill_iventory(
        "liquidpump",
        "Inventory",
        "liq",
        {
            "volume": 10e-6,
            "initial_species": {"reagent_a": 1e-4, "solvent": 3.4e-2},
        },
    )

    platform.fill_iventory(
        "liquidrecicly",
        "Inventory",
        "liq",
        {
            "volume": 10e-6,
            "initial_species": {"solvent": 3.4e-2},
        },
    )

    platform.fill_iventory("liquidrecicly", "Inventory", "gas", {"volume": 0.0})

    # ── Connections ────────────────────────────────────────────────────────────
    platform.add_connection(
        "liquidrecicly", "pump", 1, 1, length="7 cm", diameter="1.5 mm"
    )
    platform.add_connection("pump", "tmixer", 2, 4, length="7 cm", diameter="1.5 mm")

    platform.add_connection("gassupply", "mfc", 1, 1, length="7 cm", diameter="1.5 mm")
    platform.add_connection("mfc", "tmixer", 2, 1, length="7 cm", diameter="1.5 mm")
    platform.add_connection(
        "liquidpump", "tmixer", 1, 2, length="14 cm", diameter="1.5 mm"
    )
    platform.add_connection(
        "tmixer", "reactortube", 3, 1, length="2 cm", diameter="2 mm"
    )
    platform.add_connection(
        "reactortube", "reactor", 2, 2, length="2 cm", diameter="2 mm"
    )
    platform.add_connection("reactor", "bpr", 3, 1, length="2 cm", diameter="1.5 mm")
    platform.add_connection(
        "bpr", "divertvalve", 2, 0, length="24 cm", diameter="1.5 mm"
    )
    platform.add_connection(
        "divertvalve", "productsink", 1, 1, length="14 cm", diameter="1.5 mm"
    )
    platform.add_connection(
        "divertvalve", "wastesink", 2, 1, length="14 cm", diameter="1.5 mm"
    )

    platform.add_connection("chiller", "reactor", 1, 4, classification="heat")

    # ── Reactions ──────────────────────────────────────────────────────────────
    platform.add_reaction(
        "reactor",
        "FirstOrderDecay",
        reactant="reagent_a",
        product="product_b",
        rate_constant=0.3,
        phase="LIQUID",
        delta_temperature_per_mol_converted=2.0,
    )
