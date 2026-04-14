from typing import Any
from chemunited.qt.elements.component.glossary import (
    # pipes
    BackPressureRegulator,
    Distributor,
    MFCComponent,
    Separator,
    Sink,
    Source,
    # vessels
    BathReactor,
    CustomFlask,
    FlowReactor,
    # sensors
    FlowMeter,
    FlowReactor,
    # valve — rotary
    FourPortDistributionValve,
    FourPortFivePositionValve,
    # assembly
    Gantry3D,
    GlassBottle,
    # analytics
    HPLCControl,
    # pumps
    HPLCPump,
    IRControl,
    LengthControl,
    Loop,
    MFCComponent,
    MSControl,
    # technical — multichannel
    MultiChannelADC,
    MultiChannelDAC,
    MultiChannelRelay,
    NMRControl,
    # thermal
    PeltierCoolerTemperatureControl,
    PhidgetBubbleSensorComponent,
    PhidgetBubbleSensorPowerComponent,
    Photoreactor,
    PhotoSensor,
    Pool,
    # technical — powers
    PowerControl,
    PowerSwitch,
    PressureControl,
    PressureGlassBottle,
    PressureSensor,
    Reactor,
    Sink,
    SixPortDistributionValve,
    SixPortTwoPositionValve,
    SixteenPortDistributionValve,
    # valve — solenoid
    SolenoidValve,
    SolenoidValve2Way,
    Source,
    SyringePump,
    TemperatureControl,
    ThreePortFourPositionValve,
    ThreePortTwoPositionValve,
    TwelvePortDistributionValve,
    TwoPortDistributionValve,
    Vial,
)
from chemunited.qt.elements.component.graph_item import GraphComponent

# Category grouping for scene layout (row = category, col = component).
# Each entry is the GraphComponent subclass; figure/data come from cls.METADATA.
LAYOUT: dict[str, list[type[GraphComponent]]] = {
    # "analytics": [
    #     HPLCControl, 
    #     IRControl,
    #     MSControl, 
    #     NMRControl
    # ],
    # "assembly": [
    #     Gantry3D, 
    #     LengthControl
    # ],
    # "pipes": [
    #     BackPressureRegulator, 
    #     Distributor, 
    #     MFCComponent, 
    #     Separator, 
    #     Sink, 
    #     Source
    # ],
    # "pumps": [
    #     HPLCPump, 
    #     SyringePump
    # ],
    # "sensors": [
    #     FlowMeter,
    #     PhidgetBubbleSensorComponent,
    #     PhotoSensor,
    #     PressureControl,
    #     PressureSensor,
    # ],
    # "multichannel": [
    #     MultiChannelADC, 
    #     MultiChannelDAC, 
    #     MultiChannelRelay
    # ],
    "powers": [
        PowerControl,
        PowerSwitch, 
        PhidgetBubbleSensorPowerComponent
    ],
    "thermal": [
        PeltierCoolerTemperatureControl, 
        #TemperatureControl
    ],
    # "valve_rotary": [
    #     FourPortDistributionValve,
    #     FourPortFivePositionValve,
    #     SixPortDistributionValve,
    #     SixPortTwoPositionValve,
    #     SixteenPortDistributionValve,
    #     ThreePortFourPositionValve,
    #     ThreePortTwoPositionValve,
    #     TwelvePortDistributionValve,
    #     TwoPortDistributionValve,
    # ],
    # "valve_solenoid": [
    #     SolenoidValve, 
    #     SolenoidValve2Way
    # ],
    "vessels": [
        BathReactor,
        CustomFlask,
        FlowReactor,
        GlassBottle,
        Loop,
        Photoreactor,
        Pool,
        PressureGlassBottle,
        Reactor,
        Vial,
    ],
}

if __name__ == "__main__":
    FIGURE = "all"
    import sys

    from PyQt5.QtWidgets import QApplication

    from chemunited.qt.shared.graph import GraphCore, SceneCore

    SPACING_X = 200
    SPACING_Y = 180

    app = QApplication(sys.argv)
    scene = SceneCore()

    if FIGURE == "all":
        for row, (category, classes) in enumerate(LAYOUT.items()):
            for col, cls in enumerate(classes):
                mode = cls.BASEMODE(
                    name=cls.__name__,
                    figure=cls.__name__,
                    position=(col * SPACING_X, row * SPACING_Y),
                    angle=0,
                )
                data = cls.METADATA.from_mode(mode)
                component = cls(data)
                scene.addItem(component)
    else:
        for row, (category, classes) in enumerate(LAYOUT.items()):
            for col, cls in enumerate(classes):
                mode = cls.BASEMODE(
                    name=cls.__name__,
                    figure=cls.__name__,
                    position=(col * SPACING_X, row * SPACING_Y),
                    angle=0,
                )
                data = cls.METADATA.from_mode(mode)
                if cls.__name__ == FIGURE:
                    component = cls(data)
                    scene.addItem(component)
                    break

    view = GraphCore(scene)
    view.show()
    sys.exit(app.exec_())
