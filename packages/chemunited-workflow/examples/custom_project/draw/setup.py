# =============================================
# Auto-generated ChemUnited Draw Setup
# Project Name: complete
# Generated on: 2026-06-24T10:06:44.543069+00:00
# ---------------------------------------------
# This file is built by ChemUnited from the open
# project canvas. Saving the project in the app
# rewrites this file.
#
# You may edit it while the project is closed.
# When the project is opened, ChemUnited calls
# build_draw(platform) to rebuild the platform.
# =============================================


def build_draw(platform):
    """Build the platform layout for this project."""
    # Component reference:
    # platform.add_component(
    #     name="PumpA",
    #     figure="HPLCPump",
    #     position=(0.0, 0.0),
    #     angle=0,
    # )
    #
    # Connection reference:
    # platform.add_connection(
    #     origin="PumpA",
    #     destiny="ReactorA",
    #     origin_port=2,
    #     destiny_port=1,
    # )
    platform.add_component(
        name="AS waste",
        figure="Sink",
        position=(-61.930056710775034, 197.36672967863902),
        angle=90,
        bottom_access=0,
        capacity="10000000000000.0 milliliter",
        diameter="0.05 meter",
        heat_exchange=False,
        heat_transfer_coefficient="1000.0 watt / kelvin / meter ** 2",
        mirror=False,
        pressure_access=False,
        surface_temperature="298.15 kelvin",
        top_access=1,
    )

    platform.add_component(
        name="Waste",
        figure="Sink",
        position=(1024.5548512115704, -257.4278391014535),
        angle=0,
        bottom_access=0,
        capacity="10000000000000.0 milliliter",
        diameter="0.05 meter",
        heat_exchange=False,
        heat_transfer_coefficient="1000.0 watt / kelvin / meter ** 2",
        mirror=False,
        pressure_access=False,
        surface_temperature="298.15 kelvin",
        top_access=1,
    )

    platform.add_component(
        name="A",
        figure="GlassBottle",
        position=(395.3070148577734, -642.9557465957498),
        angle=0,
        bottom_access=1,
        capacity="10.0 milliliter",
        diameter="0.05 meter",
        heat_exchange=False,
        heat_transfer_coefficient="1000.0 watt / kelvin / meter ** 2",
        mirror=False,
        pressure_access=True,
        surface_temperature="298.15 kelvin",
        top_access=2,
    )

    platform.add_component(
        name="B",
        figure="GlassBottle",
        position=(493.7059765662242, -639.8026951791617),
        angle=0,
        bottom_access=1,
        capacity="10.0 milliliter",
        diameter="0.05 meter",
        heat_exchange=False,
        heat_transfer_coefficient="1000.0 watt / kelvin / meter ** 2",
        mirror=False,
        pressure_access=True,
        surface_temperature="298.15 kelvin",
        top_access=2,
    )

    platform.add_component(
        name="C",
        figure="GlassBottle",
        position=(581.554468860752, -642.1096877144596),
        angle=0,
        bottom_access=1,
        capacity="10.0 milliliter",
        diameter="0.05 meter",
        heat_exchange=False,
        heat_transfer_coefficient="1000.0 watt / kelvin / meter ** 2",
        mirror=False,
        pressure_access=True,
        surface_temperature="298.15 kelvin",
        top_access=2,
    )

    platform.add_component(
        name="D",
        figure="GlassBottle",
        position=(668.1541844855092, -642.8828546343915),
        angle=0,
        bottom_access=1,
        capacity="10.0 milliliter",
        diameter="0.05 meter",
        heat_exchange=False,
        heat_transfer_coefficient="1000.0 watt / kelvin / meter ** 2",
        mirror=False,
        pressure_access=True,
        surface_temperature="298.15 kelvin",
        top_access=2,
    )

    platform.add_component(
        name="Quencher",
        figure="GlassBottle",
        position=(828.3037288103643, -438.83408583122895),
        angle=0,
        bottom_access=1,
        capacity="10.0 milliliter",
        diameter="0.05 meter",
        heat_exchange=False,
        heat_transfer_coefficient="1000.0 watt / kelvin / meter ** 2",
        mirror=False,
        pressure_access=True,
        surface_temperature="298.15 kelvin",
        top_access=2,
    )

    platform.add_component(
        name="Tray",
        figure="Vial",
        position=(191.0185371165827, 342.2362487578619),
        angle=0,
        bottom_access=0,
        capacity="10.0 milliliter",
        column=3,
        diameter="0.01 meter",
        heat_exchange=True,
        heat_transfer_coefficient="1000.0 watt / kelvin / meter ** 2",
        mirror=False,
        pressure_access=True,
        row=2,
        surface_temperature="298.15 kelvin",
        top_access=1,
    )

    platform.add_component(
        name="solvent",
        figure="GlassBottle",
        position=(1096.1704010177464, -103.94689997694647),
        angle=0,
        bottom_access=1,
        capacity="50.0 milliliter",
        diameter="0.05 meter",
        heat_exchange=False,
        heat_transfer_coefficient="1000.0 watt / kelvin / meter ** 2",
        mirror=False,
        pressure_access=True,
        surface_temperature="298.15 kelvin",
        top_access=2,
    )

    platform.add_component(
        name="BathReactor",
        figure="CustomFlask",
        position=(1002.3238946183124, -135.4409759698649),
        angle=0,
        bottom_access=2,
        capacity="20.0 milliliter",
        diameter="0.05 meter",
        heat_exchange=True,
        heat_transfer_coefficient="1000.0 watt / kelvin / meter ** 2",
        mirror=False,
        pressure_access=False,
        surface_temperature="298.15 kelvin",
        top_access=3,
    )

    platform.add_component(
        name="Collector",
        figure="GlassBottle",
        position=(1183.0, 243.0),
        angle=0,
        bottom_access=1,
        capacity="1.0 milliliter",
        diameter="0.05 meter",
        heat_exchange=False,
        heat_transfer_coefficient="1000.0 watt / kelvin / meter ** 2",
        mirror=False,
        pressure_access=False,
        surface_temperature="298.15 kelvin",
        top_access=1,
    )

    platform.add_component(
        name="Reactor D",
        figure="Distributor",
        position=(163.92581155351084, -299.3777161070933),
        angle=0,
        mirror=False,
        number_ports=3,
    )

    platform.add_component(
        name="Quencher D",
        figure="Distributor",
        position=(421.13886000634494, -299.28195756990414),
        angle=0,
        mirror=False,
        number_ports=3,
    )

    platform.add_component(
        name="AS loop",
        figure="Loop",
        position=(101.14744801512288, -4.029569284617246),
        angle=0,
        diameter="1.0 millimeter",
        length="100.0 millimeter",
        mirror=False,
    )

    platform.add_component(
        name="Reagent loop",
        figure="Loop",
        position=(47.85327538819272, -639.8918565656467),
        angle=0,
        diameter="1.0 millimeter",
        length="100.0 millimeter",
        mirror=False,
    )

    platform.add_component(
        name="Pressure D",
        figure="Distributor",
        position=(744.86700240221, -739.8736893147038),
        angle=0,
        mirror=False,
        number_ports=7,
    )

    platform.add_component(
        name="back pressure",
        figure="BackPressureRegulator",
        position=(660.0117207125259, -312.42977705402035),
        angle=0,
        mirror=False,
        setpoint="1.0 bar",
    )

    platform.add_component(
        name="CollectorD",
        figure="Distributor",
        position=(1093.587592573329, 188.20127008889938),
        angle=0,
        mirror=False,
        number_ports=4,
    )

    platform.add_component(
        name="air",
        figure="Source",
        position=(972.5244789506725, -347.4600666421498),
        angle=0,
        mirror=False,
        setpoint="1.0 bar",
    )

    platform.add_component(
        name="quencher reactor",
        figure="FlowReactor",
        position=(526.4114880259413, -263.74497119424825),
        angle=0,
        diameter="0.001 meter",
        heat_exchange=True,
        heat_transfer_coefficient="1000.0 watt / kelvin / meter ** 2",
        length="100.0 millimeter",
        mirror=False,
        temperature="298.0 kelvin",
    )

    platform.add_component(
        name="AS injection",
        figure="SixPortTwoPositionValve",
        position=(274.2197345968068, -35.82152617975106),
        angle=0,
        mirror=False,
        rotor_ports=[[7, 7, 8, 8, 9, 9], [None]],
        stator_ports=[[1, 2, 3, 4, 5, 6], [0]],
    )

    platform.add_component(
        name="AS SP valve",
        figure="ThreePortFourPositionValve",
        position=(-59.7734414305632, -203.11915124022315),
        angle=0,
        mirror=False,
        rotor_ports=[[4, 4, 5, 5], [4]],
        stator_ports=[[None, 1, 2, 3], [0]],
    )

    platform.add_component(
        name="AS Distribution valve",
        figure="FourPortDistributionValve",
        position=(-62.323261323395926, 41.01675683070391),
        angle=0,
        mirror=False,
        rotor_ports=[[5, None, None, None], [5]],
        stator_ports=[[1, 2, 3, 4], [0]],
    )

    platform.add_component(
        name="Reagent Valve",
        figure="SixPortDistributionValve",
        position=(207.6197388500001, -597.9236408492188),
        angle=0,
        mirror=False,
        rotor_ports=[[7, None, None, None, None, None], [7]],
        stator_ports=[[1, 2, 3, 4, 5, 6], [0]],
    )

    platform.add_component(
        name="Disposal valve",
        figure="SixPortTwoPositionValve",
        position=(819.7798199838476, -201.67679019098762),
        angle=0,
        mirror=False,
        rotor_ports=[[7, 7, 8, 8, 9, 9], [None]],
        stator_ports=[[1, 2, 3, 4, 5, 6], [0]],
    )

    platform.add_component(
        name="S valve",
        figure="SolenoidValve",
        position=(855.8098117500373, -744.2845559599381),
        angle=0,
        mirror=False,
        normally_open=True,
        opened=True,
    )

    platform.add_component(
        name="S2way",
        figure="SolenoidValve2Way",
        position=(963.402306199922, -261.44240606050937),
        angle=0,
        mirror=True,
        normally_open=True,
        opened=True,
    )

    platform.add_component(
        name="Quencher valve",
        figure="SixPortDistributionValve",
        position=(554.6499231725362, -449.69280205211516),
        angle=0,
        mirror=False,
        rotor_ports=[[7, None, None, None, None, None], [7]],
        stator_ports=[[1, 2, 3, 4, 5, 6], [0]],
    )

    platform.add_component(
        name="gantry",
        figure="Gantry3D",
        position=(274.48831096408315, 162.1782908790169),
        angle=0,
        connections_number=40,
        mirror=False,
        position_x="1",
        position_y="A",
        position_z="UP",
    )

    platform.add_component(
        name="AS pump",
        figure="SyringePump",
        position=(101.78846016304347, -165.84722665465503),
        angle=0,
        direction_upward=True,
        flow_rate="0.0 milliliter / minute",
        mirror=False,
        syringe_actual_volume="0.0 milliliter",
        syringe_volume="10.0 milliliter",
    )

    platform.add_component(
        name="Reagent pump",
        figure="SyringePump",
        position=(-78.4959963973017, -655.6623282854898),
        angle=0,
        direction_upward=True,
        flow_rate="0.0 milliliter / minute",
        mirror=True,
        syringe_actual_volume="0.0 milliliter",
        syringe_volume="10.0 milliliter",
    )

    platform.add_component(
        name="Quencher pump",
        figure="SyringePump",
        position=(385.18686916201136, -510.1550313639262),
        angle=0,
        direction_upward=True,
        flow_rate="0.0 milliliter / minute",
        mirror=True,
        syringe_actual_volume="0.0 milliliter",
        syringe_volume="10.0 milliliter",
    )

    platform.add_component(
        name="chiller",
        figure="TemperatureControl",
        position=(354.0833529971966, -386.5639685873129),
        angle=0,
        mirror=False,
        temperature="298.15 kelvin",
    )

    platform.add_component(
        name="photo reactor",
        figure="PhotoReactor",
        position=(291.8301474471787, -264.3913070704955),
        angle=0,
        diameter="0.001 meter",
        heat_exchange=True,
        heat_transfer_coefficient="1000.0 watt / kelvin / meter ** 2",
        length="100.0 millimeter",
        mirror=False,
        temperature="298.0 kelvin",
    )

    platform.add_component(
        name="flowmeter",
        figure="MFCComponent",
        position=(722.8252484795468, -459.9675689907296),
        angle=0,
        flowrate="0.0 milliliter / minute",
        mirror=True,
    )

    platform.add_component(
        name="Pressure Sensor",
        figure="PressureSensor",
        position=(1070.838987117682, -383.31023370644397),
        angle=0,
        mirror=False,
    )

    platform.add_component(
        name="photo sensor",
        figure="PhotoSensor",
        position=(525.3679771987644, -191.21769333819557),
        angle=0,
        mirror=False,
    )

    platform.add_component(
        name="bubble",
        figure="PhidgetBubbleSensorComponent",
        position=(169.94910426182287, -437.2452931443163),
        angle=90,
        mirror=False,
    )

    platform.add_component(
        name="peltier",
        figure="PeltierCoolerTemperatureControl",
        position=(253.11990560122888, -387.0118294134925),
        angle=0,
        mirror=False,
        temperature="298.15 kelvin",
    )

    platform.add_component(
        name="IR",
        figure="IRControl",
        position=(828.237525744336, -14.68693546516727),
        angle=0,
        mirror=False,
    )

    platform.add_component(
        name="NMR",
        figure="NMRControl",
        position=(1195.8278191374084, 69.50591603856128),
        angle=0,
        mirror=False,
    )

    platform.add_component(
        name="HPLC",
        figure="HPLCControl",
        position=(528.0305913822368, -5.219136202456362),
        angle=0,
        mirror=False,
    )

    platform.add_component(
        name="MS",
        figure="MSControl",
        position=(720.1263200407809, 304.2870883531422),
        angle=0,
        mirror=False,
    )

    platform.add_component(
        name="HPLCpump",
        figure="HPLCPump",
        position=(666.0684824333991, 166.11159138807818),
        angle=0,
        flow_rate="0.0 milliliter / minute",
        mirror=False,
    )

    platform.add_component(
        name="Relay",
        figure="MultiChannelRelay",
        position=(998.065077929267, -542.0502203867263),
        angle=0,
        channels=8,
        mirror=False,
    )

    platform.add_component(
        name="Swicth",
        figure="PowerSwitch",
        position=(53.32973355825884, -485.808217130384),
        angle=0,
        mirror=False,
    )

    platform.add_component(
        name="Control",
        figure="PowerControl",
        position=(53.625274827527484, -329.1178274790004),
        angle=0,
        mirror=False,
    )

    platform.add_component(
        name="BubblePower",
        figure="PhidgetBubbleSensorPowerComponent",
        position=(54.08249269000931, -406.49897813387275),
        angle=0,
        mirror=False,
    )

    platform.add_component(
        name="PressureControl",
        figure="PressureControl",
        position=(947.424458859934, -758.0938644058732),
        angle=0,
        mirror=True,
        setpoint="1.0 bar",
    )

    platform.add_component(
        name="MSPump",
        figure="HPLCPump",
        position=(663.5912075978924, 41.37359746457477),
        angle=0,
        flow_rate="0.0 milliliter / minute",
        mirror=False,
    )

    platform.add_component(
        name="NMRPump",
        figure="HPLCPump",
        position=(1097.0, 27.0),
        angle=0,
        flow_rate="0.0 milliliter / minute",
        mirror=False,
    )

    platform.add_component(
        name="StirringControl",
        figure="StirringControl",
        position=(825.7369668476679, -326.57764283685896),
        angle=0,
        mirror=False,
        set_point=0,
    )

    platform.add_component(
        name="pt100",
        figure="HeiConnectTemperatureControl",
        position=(809.8063501239187, -487.2113614679969),
        angle=0,
        mirror=False,
        temperature="298.15 kelvin",
    )

    platform.add_connection(
        origin="A",
        destiny="Reagent Valve",
        origin_port=2,
        destiny_port=4,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[
            [395.21337685388676, -726.9396937224842],
            [338.4165578519435, -730.4316672858515],
            [341.51814835097184, -551.1776540675351],
        ],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="B",
        destiny="Reagent Valve",
        origin_port=2,
        destiny_port=3,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[
            [492.0634928027231, -750.8631680141903],
            [321.49225092097254, -748.8934044317045],
            [321.7066299800973, -576.4085226404618],
        ],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="C",
        destiny="Reagent Valve",
        origin_port=2,
        destiny_port=2,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[
            [582.5877389499872, -763.8666642818391],
            [250.00437399460446, -760.6701525655291],
        ],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="D",
        destiny="Reagent Valve",
        origin_port=2,
        destiny_port=1,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[
            [670.4369616677546, -779.8532477418054],
            [209.02835025887742, -777.1384442955118],
        ],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="D",
        destiny="Pressure D",
        origin_port=1,
        destiny_port=5,
        air_pressure_line=True,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="B",
        destiny="Pressure D",
        origin_port=1,
        destiny_port=7,
        air_pressure_line=True,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[[517.5680978674234, -756.9019300821739]],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="A",
        destiny="Pressure D",
        origin_port=1,
        destiny_port=1,
        air_pressure_line=True,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[[417.63204716917977, -770.7012710869067]],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Reagent Valve",
        destiny="Pressure D",
        origin_port=6,
        destiny_port=2,
        air_pressure_line=True,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[
            [163.54550641037247, -798.5677534011651],
            [774.6102853635668, -802.186348923497],
        ],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="C",
        destiny="Pressure D",
        origin_port=1,
        destiny_port=6,
        air_pressure_line=True,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[[604.5973735836482, -734.4923843609428]],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Reagent pump",
        destiny="Reagent loop",
        origin_port=1,
        destiny_port=1,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Reagent loop",
        destiny="Reagent Valve",
        origin_port=2,
        destiny_port=0,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[[175.46059670515217, -645.164751456491]],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Reagent Valve",
        destiny="bubble",
        origin_port=5,
        destiny_port=2,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="bubble",
        destiny="Reactor D",
        origin_port=1,
        destiny_port=1,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Reactor D",
        destiny="photo reactor",
        origin_port=2,
        destiny_port=1,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="photo reactor",
        destiny="Quencher D",
        origin_port=2,
        destiny_port=3,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Quencher D",
        destiny="quencher reactor",
        origin_port=2,
        destiny_port=1,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Quencher D",
        destiny="Quencher valve",
        origin_port=1,
        destiny_port=5,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[[421.41938318461854, -422.49091029258756]],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Quencher pump",
        destiny="Quencher valve",
        origin_port=1,
        destiny_port=1,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="flowmeter",
        destiny="Quencher",
        origin_port=1,
        destiny_port=2,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[[769.1083579847486, -493.9171636457692]],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="flowmeter",
        destiny="Quencher valve",
        origin_port=2,
        destiny_port=3,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="quencher reactor",
        destiny="back pressure",
        origin_port=2,
        destiny_port=1,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="back pressure",
        destiny="Disposal valve",
        origin_port=2,
        destiny_port=6,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[[708.9940042631313, -229.06231905825967]],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Disposal valve",
        destiny="IR",
        origin_port=5,
        destiny_port=1,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[
            [747.2240894555413, -178.59205225808728],
            [749.6318640620747, -18.502200081541275],
        ],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="IR",
        destiny="Disposal valve",
        origin_port=2,
        destiny_port=2,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[
            [913.5236618908236, -17.59141041663368],
            [911.2633339065383, -229.20644945135524],
        ],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Disposal valve",
        destiny="S2way",
        origin_port=1,
        destiny_port=0,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="S2way",
        destiny="BathReactor",
        origin_port=2,
        destiny_port=1,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="BathReactor",
        destiny="solvent",
        origin_port=3,
        destiny_port=2,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[[1098.1415453887425, -193.06786079964678]],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="BathReactor",
        destiny="MSPump",
        origin_port=4,
        destiny_port=2,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[[989.8871352290853, 71.59296481162716]],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="MSPump",
        destiny="HPLC",
        origin_port=1,
        destiny_port=2,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="BathReactor",
        destiny="HPLCpump",
        origin_port=5,
        destiny_port=2,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[[1006.9556403216968, 195.9657424917154]],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="HPLCpump",
        destiny="MS",
        origin_port=1,
        destiny_port=1,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="HPLC",
        destiny="CollectorD",
        origin_port=1,
        destiny_port=4,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[
            [471.3090919777828, 124.49106694322154],
            [1065.948342275556, 123.34616851606046],
        ],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="MS",
        destiny="CollectorD",
        origin_port=2,
        destiny_port=3,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[[694.356956307055, 221.24417922102077]],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="gantry",
        destiny="AS injection",
        origin_port=1,
        destiny_port=4,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="AS injection",
        destiny="AS loop",
        origin_port=5,
        destiny_port=2,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="AS loop",
        destiny="AS Distribution valve",
        origin_port=1,
        destiny_port=1,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="AS pump",
        destiny="AS SP valve",
        origin_port=1,
        destiny_port=2,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="AS SP valve",
        destiny="AS Distribution valve",
        origin_port=3,
        destiny_port=0,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[[-104.19579939210242, -22.828134822907067]],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="AS waste",
        destiny="AS Distribution valve",
        origin_port=1,
        destiny_port=3,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="S2way",
        destiny="Waste",
        origin_port=1,
        destiny_port=1,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="air",
        destiny="Pressure Sensor",
        origin_port=1,
        destiny_port=2,
        air_pressure_line=True,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Pressure Sensor",
        destiny="solvent",
        origin_port=1,
        destiny_port=1,
        air_pressure_line=True,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Quencher",
        destiny="Pressure D",
        origin_port=1,
        destiny_port=4,
        air_pressure_line=True,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[
            [854.4830560594255, -572.4704426855086],
            [760.9822013172164, -569.9518045941529],
        ],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Pressure D",
        destiny="S valve",
        origin_port=3,
        destiny_port=1,
        air_pressure_line=True,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="PressureControl",
        destiny="S valve",
        origin_port=1,
        destiny_port=2,
        air_pressure_line=True,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="AS injection",
        destiny="Reactor D",
        origin_port=6,
        destiny_port=3,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[
            [229.43175692378128, -208.59962114342216],
            [134.6884031818795, -206.48866862525773],
        ],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="NMRPump",
        destiny="NMR",
        origin_port=2,
        destiny_port=1,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="CollectorD",
        destiny="NMR",
        origin_port=1,
        destiny_port=2,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[
            [1253.7077058553687, 159.85359306373033],
            [1253.2677624963885, 55.179754551145805],
        ],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="CollectorD",
        destiny="Collector",
        origin_port=2,
        destiny_port=1,
        air_pressure_line=False,
        classification="hydraulic",
        diameter="1.0 millimeter",
        inflection_points=[],
        length="100.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Tray",
        destiny="gantry",
        origin_port=1,
        destiny_port=2,
        air_pressure_line=False,
        classification="movement",
        diameter="0.0 millimeter",
        inflection_points=[],
        length="0.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Tray",
        destiny="gantry",
        origin_port=2,
        destiny_port=3,
        air_pressure_line=False,
        classification="movement",
        diameter="0.0 millimeter",
        inflection_points=[],
        length="0.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Tray",
        destiny="gantry",
        origin_port=3,
        destiny_port=4,
        air_pressure_line=False,
        classification="movement",
        diameter="0.0 millimeter",
        inflection_points=[],
        length="0.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Tray",
        destiny="gantry",
        origin_port=4,
        destiny_port=22,
        air_pressure_line=False,
        classification="movement",
        diameter="0.0 millimeter",
        inflection_points=[],
        length="0.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Tray",
        destiny="gantry",
        origin_port=5,
        destiny_port=23,
        air_pressure_line=False,
        classification="movement",
        diameter="0.0 millimeter",
        inflection_points=[],
        length="0.0 millimeter",
        straight_path=True,
    )

    platform.add_connection(
        origin="Tray",
        destiny="gantry",
        origin_port=6,
        destiny_port=24,
        air_pressure_line=False,
        classification="movement",
        diameter="0.0 millimeter",
        inflection_points=[],
        length="0.0 millimeter",
        straight_path=True,
    )
