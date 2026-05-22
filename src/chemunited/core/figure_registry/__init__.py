from chemunited.core.components import (
    BackPressureRegulatorData,
    BackPressureRegulatorMode,
    ComponentData,
    ComponentMode,
    FlowSourceData,
    FlowSourceMode,
    Gantry3DData,
    Gantry3DMode,
    JunctionData,
    JunctionMode,
    NeutralComponentData,
    PlugFlowComponentData,
    PlugFlowMode,
    PressureControlData,
    PressureControlMode,
    VesselComponentData,
    VesselMode,
)
from chemunited.core.figure_registry.pipes import (
    SeparatorData,
    SeparatorMode,
    SinkData,
    SinkMode,
    SourceData,
    SourceMode,
)
from chemunited.core.figure_registry.rotary_valve import (
    FourPortDistributionValveData,
    FourPortDistributionValveMode,
    FourPortFivePositionValveData,
    FourPortFivePositionValveMode,
    SixPortDistributionValveData,
    SixPortDistributionValveMode,
    SixPortTwoPositionValveData,
    SixPortTwoPositionValveMode,
    SixteenPortDistributionValveData,
    SixteenPortDistributionValveMode,
    ThreePortFourPositionValveData,
    ThreePortFourPositionValveMode,
    ThreePortTwoPositionValveData,
    ThreePortTwoPositionValveMode,
    TwelvePortDistributionValveData,
    TwelvePortDistributionValveMode,
    TwoPortDistributionValveData,
    TwoPortDistributionValveMode,
)
from chemunited.core.figure_registry.solenoid_valve import (
    SolenoidValve2WayData,
    SolenoidValveData,
    SolenoidValveMode,
)
from chemunited.core.figure_registry.technical import (
    MultiChannelData,
    MultiChannelMode,
)
from chemunited.core.figure_registry.thermal import (
    PeltierCoolerTemperatureControlData,
    PeltierCoolerTemperatureControlMode,
    TemperatureControlData,
    TemperatureControlMode,
)
from chemunited.core.figure_registry.vessels import (
    FlowReactorData,
    FlowReactorMode,
    GlassBottleData,
    GlassBottleMode,
    PhotoReactorData,
    PhotoReactorMode,
    VialData,
    VialMode,
)

COMPONENTS: dict[str, tuple[type[ComponentData], type[ComponentMode]]] = {
    # analytics
    "HPLCControl": (ComponentData, ComponentMode),
    "IRControl": (ComponentData, ComponentMode),
    "MSControl": (ComponentData, ComponentMode),
    "NMRControl": (ComponentData, ComponentMode),
    # assembly
    "Gantry3D": (Gantry3DData, Gantry3DMode),
    "LengthControl": (NeutralComponentData, ComponentMode),
    # pipes
    "BackPressureRegulator": (
        BackPressureRegulatorData,
        BackPressureRegulatorMode,
    ),
    "Distributor": (JunctionData, JunctionMode),
    "MFCComponent": (ComponentData, ComponentMode),
    "Sink": (SinkData, SinkMode),
    "Source": (SourceData, SourceMode),
    "Separator": (SeparatorData, SeparatorMode),
    # pumps
    # FLAGGED: no core-specific HPLCPump data/mode yet.
    "HPLCPump": (ComponentData, ComponentMode),
    "SyringePump": (FlowSourceData, FlowSourceMode),
    # sensors
    "FlowMeter": (ComponentData, ComponentMode),
    "PhidgetBubbleSensorComponent": (ComponentData, ComponentMode),
    "PhidgetBubbleSensorPowerComponent": (NeutralComponentData, ComponentMode),
    "PhotoSensor": (NeutralComponentData, ComponentMode),
    "PressureControl": (PressureControlData, PressureControlMode),
    "PressureSensor": (ComponentData, ComponentMode),
    # technical
    "MultiChannelADC": (MultiChannelData, MultiChannelMode),
    "MultiChannelDAC": (MultiChannelData, MultiChannelMode),
    "MultiChannelRelay": (MultiChannelData, MultiChannelMode),
    "PowerControl": (NeutralComponentData, ComponentMode),
    "PowerSwitch": (NeutralComponentData, ComponentMode),
    # thermal
    "PeltierCoolerTemperatureControl": (
        PeltierCoolerTemperatureControlData,
        PeltierCoolerTemperatureControlMode,
    ),
    "TemperatureControl": (TemperatureControlData, TemperatureControlMode),
    # valve - rotary
    "FourPortDistributionValve": (
        FourPortDistributionValveData,
        FourPortDistributionValveMode,
    ),
    "FourPortFivePositionValve": (
        FourPortFivePositionValveData,
        FourPortFivePositionValveMode,
    ),
    "SixPortDistributionValve": (
        SixPortDistributionValveData,
        SixPortDistributionValveMode,
    ),
    "SixPortTwoPositionValve": (
        SixPortTwoPositionValveData,
        SixPortTwoPositionValveMode,
    ),
    "SixteenPortDistributionValve": (
        SixteenPortDistributionValveData,
        SixteenPortDistributionValveMode,
    ),
    "ThreePortFourPositionValve": (
        ThreePortFourPositionValveData,
        ThreePortFourPositionValveMode,
    ),
    "ThreePortTwoPositionValve": (
        ThreePortTwoPositionValveData,
        ThreePortTwoPositionValveMode,
    ),
    "TwelvePortDistributionValve": (
        TwelvePortDistributionValveData,
        TwelvePortDistributionValveMode,
    ),
    "TwoPortDistributionValve": (
        TwoPortDistributionValveData,
        TwoPortDistributionValveMode,
    ),
    # valve - solenoid
    "SolenoidValve": (SolenoidValveData, SolenoidValveMode),
    "SolenoidValve2Way": (SolenoidValve2WayData, SolenoidValveMode),
    # vessels
    "CustomFlask": (VesselComponentData, VesselMode),
    "FlowReactor": (FlowReactorData, FlowReactorMode),
    "GlassBottle": (GlassBottleData, GlassBottleMode),
    "Loop": (PlugFlowComponentData, PlugFlowMode),
    "PhotoReactor": (PhotoReactorData, PhotoReactorMode),
    "Vial": (VialData, VialMode),
}
