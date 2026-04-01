from chemunited.qt.shared.elements.component.glossary import (
    # analytics
    HPLCControl, IRControl, MSControl, NMRControl,
    # assembly
    Gantry3D, LengthControl,
    # pipes
    BackPressureRegulator, Distributor, MFCComponent, Sink, Source,
    # pumps
    HPLCPump, SyringePump,
    # sensors
    FlowMeter, PhidgetBubbleSensorComponent, PhotoSensor, PressureControl, PressureSensor,
    # technical — multichannel
    MultiChannelADC, MultiChannelDAC, MultiChannelRelay,
    # technical — powers
    PowerControl, PowerSwitch, PhidgetBubbleSensorPowerComponent,
    # thermal
    PeltierCoolerTemperatureControl, TemperatureControl,
    # valve — rotary
    FourPortDistributionValve, FourPortFivePositionValve,
    SixPortDistributionValve, SixPortTwoPositionValve,
    SixteenPortDistributionValve, ThreePortFourPositionValve,
    ThreePortTwoPositionValve, TwelvePortDistributionValve, TwoPortDistributionValve,
    # valve — solenoid
    SolenoidValve, SolenoidValve2Way,
    # vessels
    BathReactor, CustomFlask, FlowReactor, GlassBottle, Loop,
    Photoreactor, Pool, PressureGlassBottle, Reactor, Vial,
)
from chemunited.qt.shared.elements.component.graph_item import GraphComponent

# Category grouping for scene layout (row = category, col = component).
# Each entry is the GraphComponent subclass; figure/data come from cls.METADATA.
LAYOUT: dict[str, list[type[GraphComponent]]] = {
    "analytics":   [HPLCControl, IRControl, MSControl, NMRControl],
    "assembly":    [Gantry3D, LengthControl],
    "pipes":       [BackPressureRegulator, Distributor, MFCComponent, Sink, Source],
    "pumps":       [HPLCPump, SyringePump],
    "sensors":     [FlowMeter, PhidgetBubbleSensorComponent, PhotoSensor, PressureControl, PressureSensor],
    "multichannel":[MultiChannelADC, MultiChannelDAC, MultiChannelRelay],
    "powers":      [PowerControl, PowerSwitch, PhidgetBubbleSensorPowerComponent],
    "thermal":     [PeltierCoolerTemperatureControl, TemperatureControl],
    "valve_rotary":[
        FourPortDistributionValve, FourPortFivePositionValve,
        SixPortDistributionValve, SixPortTwoPositionValve,
        SixteenPortDistributionValve, ThreePortFourPositionValve,
        ThreePortTwoPositionValve, TwelvePortDistributionValve, TwoPortDistributionValve,
    ],
    "valve_solenoid": [SolenoidValve, SolenoidValve2Way],
    "vessels":     [BathReactor, CustomFlask, FlowReactor, GlassBottle, Loop,
                    Photoreactor, Pool, PressureGlassBottle, Reactor, Vial],
}

if __name__ == "__main__":
    from chemunited.qt.shared.graph import GraphCore, SceneCore
    from PyQt5.QtWidgets import QApplication
    import sys
    
    SPACING_X = 200
    SPACING_Y = 180

    app = QApplication(sys.argv)
    scene = SceneCore()

    for row, (category, classes) in enumerate(LAYOUT.items()):
        for col, cls in enumerate(classes):
            component = cls(
                data=cls.METADATA(
                    name=cls.__name__,
                    figure=cls.__name__,
                    position=(col * SPACING_X, row * SPACING_Y),
                    angle=0,
                ),
            )
            scene.addItem(component)

    view = GraphCore(scene)
    view.show()
    sys.exit(app.exec_())