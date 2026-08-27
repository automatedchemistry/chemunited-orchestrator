# Components available

This page is a visual glossary of every component type available in the **Draw** canvas, grouped by category.
Use it to quickly recognize a component's icon while building a platform, or to check what a given component
represents physically before adding it to your setup.

<div class="info-block">
<strong>💡 Note</strong><br>
Every icon below can be dragged onto the canvas from the component tree described in
<a href="../drawing/drawing.md">Drawing</a>. Component names shown here match the class names used internally,
so they are also what you will see referenced in generated protocol code. Some components share the same icon —
for example, all rotary valve variants are drawn with the same base graphic, and <strong>Source</strong>/
<strong>Sink</strong> use the same icon mirrored.
</div>

## Analytics

| Icon | Component | Description |
|---|---|---|
| <img src="../_static/components/HPLC.svg" width="40" height="40"> | **HPLC Control** | Controls an HPLC instrument (injection, method, run control) as part of the platform. |
| <img src="../_static/components/IRControl.svg" width="40" height="40"> | **IR Control** | Interfaces with an in-line infrared (IR) spectrometer for reaction monitoring. |
| <img src="../_static/components/MSControl.svg" width="40" height="40"> | **MS Control** | Interfaces with a mass spectrometer for in-line analysis. |
| <img src="../_static/components/NMRControl.svg" width="40" height="40"> | **NMR Control** | Interfaces with a benchtop or in-line NMR instrument. |

## Assembly

| Icon | Component | Description |
|---|---|---|
| <img src="../_static/components/Gantry.svg" width="40" height="40"> | **3D Gantry** | Motorized 3-axis gantry/stage for positioning tools or vessels. |
| <img src="../_static/components/LengthControl.svg" width="40" height="40"> | **Length Control** | Controls a linear-position actuator (e.g. a gantry axis or motorized stage). |

## Pipes

| Icon | Component | Description |
|---|---|---|
| <img src="../_static/components/BackPressureRegulator.svg" width="40" height="40"> | **Back-Pressure Regulator** | Holds upstream line pressure at a setpoint, keeping the system pressurized (e.g. to prevent gas evolution/boiling). |
| <img src="../_static/components/Distributor.svg" width="40" height="40"> | **Distributor** | Routes flow from one inlet to a selectable outlet among several ports. |
| <img src="../_static/components/MassFlowControl.svg" width="40" height="40"> | **Mass Flow Controller** | Actively regulates gas/liquid flow rate to a setpoint. |
| <img src="../_static/components/Separator.svg" width="40" height="40"> | **Separator** | Separates two phases (e.g. liquid/liquid or gas/liquid) at a junction. |
| <img src="../_static/components/SourceSink.svg" width="40" height="40"> | **Source** | Abstract infinite liquid/gas source, used when the exact upstream vessel is not modeled in detail. |
| <img src="../_static/components/SourceSink.svg" width="40" height="40"> | **Sink** | Abstract infinite drain/waste point, used when the exact downstream destination is not modeled in detail. |

## Pumps

| Icon | Component | Description |
|---|---|---|
| <img src="../_static/components/HPLCPump.svg" width="40" height="40"> | **HPLC Pump** | High-pressure liquid pump typically used for continuous-flow delivery against packed-bed backpressure. |
| <img src="../_static/components/SyringeBarrel.svg" width="40" height="40"> | **Syringe Pump** | Infuses or withdraws liquid at a controlled rate from a syringe barrel; the most common liquid-delivery component. |

## Sensors

| Icon | Component | Description |
|---|---|---|
| <img src="../_static/components/FlowMeter.svg" width="40" height="40"> | **Flowmeter** | Measures the flow rate of liquid or gas passing through a line. |
| <img src="../_static/components/BubbleSensor.svg" width="40" height="40"> | **Phidget Bubble Sensor** | Optical sensor that detects gas bubbles/phase boundaries in a tube (Phidget hardware). |
| <img src="../_static/components/Power.svg" width="40" height="40"> | **Phidget Bubble Sensor (Powered)** | Powered variant of the Phidget bubble sensor, with an associated power/control channel. |
| <img src="../_static/components/PhotoSensor.svg" width="40" height="40"> | **Photo Sensor** | General-purpose optical sensor for detecting light level or phase changes. |
| <img src="../_static/components/PressureControl.svg" width="40" height="40"> | **Pressure Control** | Actively controls pressure at a setpoint (e.g. driving a pressurizing device). |
| <img src="../_static/components/PressureSensor.svg" width="40" height="40"> | **Pressure Sensor** | Measures line or vessel pressure. |
| <img src="../_static/components/PT100.svg" width="40" height="40"> | **Temperature Sensor** | Measures temperature at a line or vessel without controlling it. |

## Technical

| Icon | Component | Description |
|---|---|---|
| <img src="../_static/components/ADC.svg" width="40" height="40"> | **Multi-Channel ADC** | Analog-to-digital converter for reading multiple analog signals (e.g. voltages from sensors). |
| <img src="../_static/components/DAC.svg" width="40" height="40"> | **Multi-Channel DAC** | Digital-to-analog converter for driving multiple analog outputs. |
| <img src="../_static/components/Relay.svg" width="40" height="40"> | **Multi-Channel Relay** | Bank of electronic relays for switching multiple devices/power lines on and off. |
| <img src="../_static/components/Power.svg" width="40" height="40"> | **Power Control** | Controls the power level/output of a connected device. |
| <img src="../_static/components/Power.svg" width="40" height="40"> | **Power Switch** | Simple on/off power control for a connected device. |
| <img src="../_static/components/Stirring.svg" width="40" height="40"> | **Stirring Control** | Controls a stirring/mixing device (e.g. a magnetic or overhead stirrer). |

## Thermal

| Icon | Component | Description |
|---|---|---|
| <img src="../_static/components/PT100.svg" width="40" height="40"> | **HeiConnect Temperature Control** | Temperature control via a HeiConnect-style controller with a PT100 probe. |
| <img src="../_static/components/Peltier.svg" width="40" height="40"> | **Peltier Cooler Temperature Control** | Temperature control driven by a Peltier (thermoelectric) element, supporting both heating and cooling. |
| <img src="../_static/components/Chiller.svg" width="40" height="40"> | **Temperature Control** | Controls the temperature of an associated vessel or zone at a setpoint. |

## Valve

| Icon | Component | Description |
|---|---|---|
| <img src="../_static/components/RotaryValve.svg" width="40" height="40"> | **4-Port Distribution Valve** | Rotary selector valve with 4 ports for routing flow between lines. |
| <img src="../_static/components/RotaryValve.svg" width="40" height="40"> | **4-Port / 5-Position Valve** | Rotary selector valve with 4 ports and 5 selectable positions. |
| <img src="../_static/components/RotaryValve.svg" width="40" height="40"> | **6-Port Distribution Valve** | Rotary selector valve with 6 ports for routing flow between lines. |
| <img src="../_static/components/RotaryValve.svg" width="40" height="40"> | **6-Port / 2-Position Valve** | Common rotary injection/switching valve (e.g. sample loop loading) with 6 ports and 2 positions. |
| <img src="../_static/components/RotaryValve.svg" width="40" height="40"> | **16-Port Distribution Valve** | High-channel-count rotary selector valve for routing between many lines (e.g. multi-reagent selection). |
| <img src="../_static/components/RotaryValve.svg" width="40" height="40"> | **3-Port / 4-Position Valve** | Rotary selector valve with 3 ports and 4 selectable positions. |
| <img src="../_static/components/RotaryValve.svg" width="40" height="40"> | **3-Port / 2-Position Valve** | Rotary selector valve with 3 ports and 2 selectable positions, commonly used to divert flow to waste or collection. |
| <img src="../_static/components/RotaryValve.svg" width="40" height="40"> | **12-Port Distribution Valve** | Rotary selector valve with 12 ports for routing between many lines. |
| <img src="../_static/components/RotaryValve.svg" width="40" height="40"> | **2-Port Distribution Valve** | Simple rotary selector valve with 2 ports. |
| <img src="../_static/components/SolenoidValve.svg" width="40" height="40"> | **Solenoid Valve** | Electronically actuated on/off valve. |
| <img src="../_static/components/SolenoidValve2Way.svg" width="40" height="40"> | **2-Way Solenoid Valve** | On/off solenoid valve with a single flow path between two ports. |

## Vessel

| Icon | Component | Description |
|---|---|---|
| <img src="../_static/components/CustomFlask.svg" width="40" height="40"> | **Custom Flask** | Generic user-defined flask/vessel for holding or mixing liquids. |
| <img src="../_static/components/FlowReactorBase.svg" width="40" height="40"> | **Flow Reactor** | Coil or chip-based reactor for continuous-flow reactions with a defined residence volume. |
| <img src="../_static/components/GlassBottle.svg" width="40" height="40"> | **Glass Bottle** | Reagent or solvent storage vessel, typically used as a source/reservoir. |
| <img src="../_static/components/LoopBase.svg" width="40" height="40"> | **Loop** | Fixed-volume sample loop, typically paired with a selector valve for injection. |
| <img src="../_static/components/FlowReactorBase.svg" width="40" height="40"> | **Photo Reactor** | Reactor equipped with a light source for photochemical reactions (shares its base figure with Flow Reactor). |
| <img src="../_static/components/Vial.svg" width="40" height="40"> | **Vial** | Small-volume vessel, typically used for sample storage or collection. |

---

Looking for how to build a component that isn't in this list? See
[Add new components](../developer/add_components.md) in the Developer section.
