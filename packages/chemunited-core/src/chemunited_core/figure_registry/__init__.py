import inspect as _inspect
from dataclasses import dataclass as _dataclass
from dataclasses import field as _field
from importlib.resources import files as _pkg_files
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Iterator

from chemunited_core.components import (
    BackPressureRegulatorData,
    BackPressureRegulatorMode,
    ComponentData,
    ComponentMode,
    JunctionData,
    JunctionMode,
    MassFlowControllerMode,
    NeutralComponentData,
    PlugFlowComponentData,
    PlugFlowMode,
    PressureControlData,
    PressureControlMode,
    PumpMode,
    VesselComponentData,
    VesselMode,
)
from chemunited_core.components import (
    FlowSourceMode as FlowSourceMode,
)
from chemunited_core.figure_registry.assemble import (
    Gantry1DData,
    Gantry1DMode,
    Gantry3DData,
    Gantry3DMode,
)
from chemunited_core.figure_registry.controllers import MFCComponentData
from chemunited_core.figure_registry.pipes import (
    SeparatorData,
    SeparatorMode,
    SinkData,
    SinkMode,
    SourceData,
    SourceMode,
)
from chemunited_core.figure_registry.pumps import (
    HPLCPumpData,
    SyringePumpData,
    SyringePumpMode,
)
from chemunited_core.figure_registry.rotary_valve import (
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
from chemunited_core.figure_registry.solenoid_valve import (
    SolenoidValve2WayData,
    SolenoidValve2WayMode,
    SolenoidValveData,
    SolenoidValveMode,
)
from chemunited_core.figure_registry.technical import (
    MultiChannelData,
    MultiChannelMode,
    MultiChannelRelayData,
    StirringControlData,
    StirringControlMode,
)
from chemunited_core.figure_registry.thermal import (
    HeiConnectTemperatureControlData,
    HeiConnectTemperatureControlMode,
    PeltierCoolerTemperatureControlData,
    PeltierCoolerTemperatureControlMode,
    TemperatureControlData,
    TemperatureControlMode,
)
from chemunited_core.figure_registry.vessels import (
    FlowReactorData,
    FlowReactorMode,
    GlassBottleData,
    GlassBottleMode,
    PhotoReactorData,
    PhotoReactorMode,
    VialData,
    VialMode,
)


@_dataclass(frozen=True)
class ComponentDefinition:
    """Canonical definition for a figure in the registry.

    data_class:     runtime data container for this component type.
    mode_class:     user-editable parameter schema.
    figure_base:    primary SVG asset name (without .svg). Empty = same as the dict key.
    svg_scale:      multiplier applied to PATTERN_DIMENSION when rendering
                    the primary SVG.
    svg_rotation:   degrees to rotate the primary SVG after loading (0 = no rotation).
    port_positions: visual (x, y) overrides for port connection points,
                    keyed by port number.
                    Empty = use the data class internal_structure() defaults.
    category:       palette grouping for frontend organisation
                    (e.g. "pipes", "sensors").
    """

    data_class: type[ComponentData]
    mode_class: type[ComponentMode]
    figure_base: str = ""
    svg_scale: float = 2.0
    svg_rotation: float = 0.0
    port_positions: dict[int, tuple[float, float]] = _field(default_factory=dict)
    category: str = ""

    def __iter__(self) -> Iterator[type[ComponentData] | type[ComponentMode]]:
        """Allow legacy tuple unpacking into data and mode classes."""
        yield self.data_class
        yield self.mode_class


__all__ = [
    # functions / constants defined here
    "COMPONENTS",
    "ComponentDefinition",
    "get_figure_svg",
    "get_figure_path",
    "list_figures",
    "register_component",
    "register_figure",
    "is_project_component",
    "clear_project_components",
    # re-exported from chemunited_core.components
    "BackPressureRegulatorData",
    "BackPressureRegulatorMode",
    "ComponentData",
    "ComponentMode",
    "FlowSourceMode",
    "JunctionData",
    "JunctionMode",
    "MassFlowControllerMode",
    "NeutralComponentData",
    "PlugFlowComponentData",
    "PlugFlowMode",
    "PressureControlData",
    "PressureControlMode",
    "PumpMode",
    "VesselComponentData",
    "VesselMode",
    # re-exported from figure_registry submodules
    "Gantry1DData",
    "Gantry1DMode",
    "Gantry3DData",
    "Gantry3DMode",
    "MFCComponentData",
    "SeparatorData",
    "SeparatorMode",
    "SinkData",
    "SinkMode",
    "SourceData",
    "SourceMode",
    "HPLCPumpData",
    "SyringePumpData",
    "SyringePumpMode",
    "FourPortDistributionValveData",
    "FourPortDistributionValveMode",
    "FourPortFivePositionValveData",
    "FourPortFivePositionValveMode",
    "SixPortDistributionValveData",
    "SixPortDistributionValveMode",
    "SixPortTwoPositionValveData",
    "SixPortTwoPositionValveMode",
    "SixteenPortDistributionValveData",
    "SixteenPortDistributionValveMode",
    "ThreePortFourPositionValveData",
    "ThreePortFourPositionValveMode",
    "ThreePortTwoPositionValveData",
    "ThreePortTwoPositionValveMode",
    "TwelvePortDistributionValveData",
    "TwelvePortDistributionValveMode",
    "TwoPortDistributionValveData",
    "TwoPortDistributionValveMode",
    "SolenoidValve2WayMode",
    "SolenoidValve2WayData",
    "SolenoidValveData",
    "SolenoidValveMode",
    "MultiChannelData",
    "MultiChannelMode",
    "MultiChannelRelayData",
    "PeltierCoolerTemperatureControlData",
    "PeltierCoolerTemperatureControlMode",
    "TemperatureControlData",
    "TemperatureControlMode",
    "FlowReactorData",
    "FlowReactorMode",
    "GlassBottleData",
    "GlassBottleMode",
    "PhotoReactorData",
    "PhotoReactorMode",
    "VialData",
    "VialMode",
]

_FIGURES = _pkg_files("chemunited_core.figure_registry.figures")
_FIGURE_ALIASES = {"Gantry3D": "Gantry"}

# Figures registered from outside the package (project-local custom components),
# keyed the same way callers already resolve names: figure_base or the
# COMPONENTS dict key. Populated by register_component().
_EXTERNAL_FIGURES: dict[str, Path] = {}

# Names of COMPONENTS entries added via register_component(), as opposed to the
# built-in catalog defined below. Used to group custom components separately
# (e.g. under a "Custom" category in the orchestrator's palette).
_PROJECT_COMPONENTS: set[str] = set()


def get_figure_svg(name: str) -> str:
    """Return SVG markup for *name* (filename without .svg extension)."""
    name = _FIGURE_ALIASES.get(name, name)
    if name in _EXTERNAL_FIGURES:
        return _EXTERNAL_FIGURES[name].read_text(encoding="utf-8")
    return _FIGURES.joinpath(f"{name}.svg").read_text(encoding="utf-8")


def get_figure_path(name: str) -> Traversable:
    """Return a Traversable for the SVG file (zip-safe; use open() or as_file())."""
    name = _FIGURE_ALIASES.get(name, name)
    if name in _EXTERNAL_FIGURES:
        return _EXTERNAL_FIGURES[name]
    return _FIGURES.joinpath(f"{name}.svg")


def list_figures() -> list[str]:
    """Return sorted list of available figure names (without .svg extension)."""
    builtin = (p.name[:-4] for p in _FIGURES.iterdir() if p.name.endswith(".svg"))
    return sorted({*builtin, *_EXTERNAL_FIGURES})


def register_figure(name: str, path: Path, *, override: bool = False) -> None:
    """Register an external SVG so get_figure_svg()/get_figure_path() can find it.

    Intended for auxiliary/composited layers a custom GraphComponent references
    directly (e.g. self._build_svg("MyValveHandle")) that don't correspond to a
    registered component figure on their own. register_component() already
    handles the primary figure automatically; use this for extra layers.
    """
    if name in _EXTERNAL_FIGURES and not override:
        raise ValueError(
            f"Figure '{name}' is already registered. Pass override=True to replace it."
        )
    _EXTERNAL_FIGURES[name] = path


def is_project_component(name: str) -> bool:
    """Return True if *name* was registered via register_component()."""
    return name in _PROJECT_COMPONENTS


def clear_project_components() -> None:
    """Remove all project-registered components (see register_component()).

    Call this at the start of each project load so switching projects
    doesn't leak a previous project's custom components into the new one.
    """
    for name in _PROJECT_COMPONENTS:
        COMPONENTS.pop(name, None)
    _PROJECT_COMPONENTS.clear()
    _EXTERNAL_FIGURES.clear()


COMPONENTS: dict[str, ComponentDefinition] = {
    # analytics
    "HPLCControl": ComponentDefinition(
        ComponentData,
        ComponentMode,
        figure_base="HPLC",
        svg_scale=4.0,
        port_positions={1: (-55, 80), 2: (55, 80)},
        category="analytics",
    ),
    "IRControl": ComponentDefinition(
        ComponentData,
        ComponentMode,
        port_positions={1: (-10, -2), 2: (10, -2)},
        category="analytics",
    ),
    "MSControl": ComponentDefinition(
        ComponentData,
        ComponentMode,
        port_positions={1: (-40, -40), 2: (-25, -40)},
        category="analytics",
    ),
    "NMRControl": ComponentDefinition(
        ComponentData,
        ComponentMode,
        port_positions={1: (-28, -10), 2: (28, -10)},
        category="analytics",
    ),
    # assembly
    "Gantry1D": ComponentDefinition(
        Gantry1DData,
        Gantry1DMode,
        figure_base="Gantry",
        svg_scale=4.0,
        category="assembly",
    ),
    "Gantry3D": ComponentDefinition(
        Gantry3DData,
        Gantry3DMode,
        figure_base="Gantry",
        svg_scale=4.0,
        category="assembly",
    ),
    "LengthControl": ComponentDefinition(
        NeutralComponentData, ComponentMode, category="assembly"
    ),
    # pipes
    "BackPressureRegulator": ComponentDefinition(
        BackPressureRegulatorData,
        BackPressureRegulatorMode,
        port_positions={1: (-50, 28), 2: (50, 28)},
        category="pipes",
    ),
    "Distributor": ComponentDefinition(
        JunctionData, JunctionMode, svg_scale=0.1, category="pipes"
    ),
    "MFCComponent": ComponentDefinition(
        MFCComponentData,
        MassFlowControllerMode,
        figure_base="MassFlowControl",
        port_positions={1: (-45, 35), 2: (45, 35)},
        category="pipes",
    ),
    "Sink": ComponentDefinition(
        SinkData,
        SinkMode,
        figure_base="SourceSink",
        svg_scale=1.0,
        port_positions={1: (-20, 0)},
        category="pipes",
    ),
    "Source": ComponentDefinition(
        SourceData,
        SourceMode,
        figure_base="SourceSink",
        svg_scale=1.0,
        svg_rotation=180.0,
        port_positions={1: (20, 0)},
        category="pipes",
    ),
    "Separator": ComponentDefinition(
        SeparatorData,
        SeparatorMode,
        port_positions={1: (-40, -26), 2: (-40, 3)},
        category="pipes",
    ),
    # pumps
    "HPLCPump": ComponentDefinition(
        HPLCPumpData,
        PumpMode,
        port_positions={1: (14, 33), 2: (35, 33)},
        category="pumps",
    ),
    "SyringePump": ComponentDefinition(
        SyringePumpData,
        SyringePumpMode,
        figure_base="SyringeBarrel",
        port_positions={1: (-50, 11.5)},
        category="pumps",
    ),
    # sensors
    "FlowMeter": ComponentDefinition(ComponentData, ComponentMode, category="sensors"),
    "PhidgetBubbleSensorComponent": ComponentDefinition(
        ComponentData,
        ComponentMode,
        figure_base="BubbleSensor",
        port_positions={1: (-48, 7), 2: (48, 7)},
        category="sensors",
    ),
    "PhidgetBubbleSensorPowerComponent": ComponentDefinition(
        NeutralComponentData,
        ComponentMode,
        figure_base="Power",
        svg_scale=0.8,
        category="sensors",
    ),
    "PhotoSensor": ComponentDefinition(
        NeutralComponentData,
        ComponentMode,
        svg_scale=0.5,
        category="sensors",
    ),
    "PressureControl": ComponentDefinition(
        PressureControlData,
        PressureControlMode,
        port_positions={1: (40, 26)},
        category="sensors",
    ),
    "PressureSensor": ComponentDefinition(
        ComponentData,
        ComponentMode,
        port_positions={1: (48, 35), 2: (-48, 35)},
        category="sensors",
    ),
    "TemperatureSensor": ComponentDefinition(
        NeutralComponentData,
        ComponentMode,
        figure_base="PT100",
        category="sensors",
    ),
    # technical
    "MultiChannelADC": ComponentDefinition(
        MultiChannelData,
        MultiChannelMode,
        figure_base="ADC",
        svg_scale=0.8,
        category="technical",
    ),
    "MultiChannelDAC": ComponentDefinition(
        MultiChannelData,
        MultiChannelMode,
        figure_base="DAC",
        svg_scale=0.8,
        category="technical",
    ),
    "MultiChannelRelay": ComponentDefinition(
        MultiChannelRelayData,
        MultiChannelMode,
        figure_base="Relay",
        svg_scale=0.8,
        category="technical",
    ),
    "PowerControl": ComponentDefinition(
        NeutralComponentData,
        ComponentMode,
        figure_base="Power",
        svg_scale=0.8,
        category="technical",
    ),
    "PowerSwitch": ComponentDefinition(
        NeutralComponentData,
        ComponentMode,
        figure_base="Power",
        svg_scale=0.8,
        category="technical",
    ),
    "StirringControl": ComponentDefinition(
        StirringControlData,
        StirringControlMode,
        figure_base="Stirring",
        svg_scale=2.0,
        category="technical",
    ),
    # thermal
    "HeiConnectTemperatureControl": ComponentDefinition(
        HeiConnectTemperatureControlData,
        HeiConnectTemperatureControlMode,
        figure_base="PT100",
        svg_scale=2.0,
        category="thermal",
    ),
    "PeltierCoolerTemperatureControl": ComponentDefinition(
        PeltierCoolerTemperatureControlData,
        PeltierCoolerTemperatureControlMode,
        figure_base="Peltier",
        svg_scale=2.0,
        category="thermal",
    ),
    "TemperatureControl": ComponentDefinition(
        TemperatureControlData,
        TemperatureControlMode,
        figure_base="Chiller",
        category="thermal",
    ),
    # valve — rotary
    "FourPortDistributionValve": ComponentDefinition(
        FourPortDistributionValveData,
        FourPortDistributionValveMode,
        figure_base="RotaryValve",
        svg_scale=4.0,
        category="valve",
    ),
    "FourPortFivePositionValve": ComponentDefinition(
        FourPortFivePositionValveData,
        FourPortFivePositionValveMode,
        figure_base="RotaryValve",
        svg_scale=4.0,
        category="valve",
    ),
    "SixPortDistributionValve": ComponentDefinition(
        SixPortDistributionValveData,
        SixPortDistributionValveMode,
        figure_base="RotaryValve",
        svg_scale=4.0,
        category="valve",
    ),
    "SixPortTwoPositionValve": ComponentDefinition(
        SixPortTwoPositionValveData,
        SixPortTwoPositionValveMode,
        figure_base="RotaryValve",
        svg_scale=4.0,
        category="valve",
    ),
    "SixteenPortDistributionValve": ComponentDefinition(
        SixteenPortDistributionValveData,
        SixteenPortDistributionValveMode,
        figure_base="RotaryValve",
        svg_scale=4.0,
        category="valve",
    ),
    "ThreePortFourPositionValve": ComponentDefinition(
        ThreePortFourPositionValveData,
        ThreePortFourPositionValveMode,
        figure_base="RotaryValve",
        svg_scale=4.0,
        category="valve",
    ),
    "ThreePortTwoPositionValve": ComponentDefinition(
        ThreePortTwoPositionValveData,
        ThreePortTwoPositionValveMode,
        figure_base="RotaryValve",
        svg_scale=4.0,
        category="valve",
    ),
    "TwelvePortDistributionValve": ComponentDefinition(
        TwelvePortDistributionValveData,
        TwelvePortDistributionValveMode,
        figure_base="RotaryValve",
        svg_scale=4.0,
        category="valve",
    ),
    "TwoPortDistributionValve": ComponentDefinition(
        TwoPortDistributionValveData,
        TwoPortDistributionValveMode,
        figure_base="RotaryValve",
        svg_scale=4.0,
        category="valve",
    ),
    # valve — solenoid
    "SolenoidValve": ComponentDefinition(
        SolenoidValveData,
        SolenoidValveMode,
        svg_scale=1.0,
        category="valve",
    ),
    "SolenoidValve2Way": ComponentDefinition(
        SolenoidValve2WayData,
        SolenoidValve2WayMode,
        svg_scale=1.0,
        category="valve",
    ),
    # vessels
    "CustomFlask": ComponentDefinition(
        VesselComponentData, VesselMode, category="vessel"
    ),
    "FlowReactor": ComponentDefinition(
        FlowReactorData,
        FlowReactorMode,
        figure_base="FlowReactorBase",
        port_positions={1: (-45, -20), 2: (45, -20)},
        category="vessel",
    ),
    "GlassBottle": ComponentDefinition(
        GlassBottleData, GlassBottleMode, category="vessel"
    ),
    "Loop": ComponentDefinition(
        PlugFlowComponentData,
        PlugFlowMode,
        figure_base="LoopBase",
        port_positions={1: (-50, -5), 2: (50, -5)},
        category="vessel",
    ),
    "PhotoReactor": ComponentDefinition(
        PhotoReactorData,
        PhotoReactorMode,
        figure_base="FlowReactorBase",
        port_positions={1: (-45, -20), 2: (45, -20)},
        category="vessel",
    ),
    "Vial": ComponentDefinition(
        VialData,
        VialMode,
        port_positions={1: (0, -11), 2: (0, 10)},
        category="vessel",
    ),
}


def register_component(
    name: str,
    definition: ComponentDefinition,
    *,
    figure_path: Path | None = None,
    override: bool = False,
) -> None:
    """Register a component definition from outside chemunited-core.

    Intended for project-local custom components (see
    ``chemunited_core.figure_registry.project_loader.load_project_components``).

    Raises ValueError if *name* is already registered, unless *override* is
    set — this catches accidental clashes with a built-in figure or another
    custom component.

    If *figure_path* is omitted, this looks for a file named
    ``<figure_base or name>.svg`` next to the caller's own source file, so a
    custom component's SVG can simply be placed alongside its Python module.
    If no such file exists, the component falls back to a built-in SVG of
    that name if one exists (letting a custom component reuse an existing
    figure), otherwise no figure is available and callers fall back to a
    placeholder shape.
    """
    if name in COMPONENTS and not override:
        raise ValueError(
            f"Component '{name}' is already registered. "
            "Pass override=True to replace it."
        )

    figure_name = definition.figure_base or name
    if figure_path is None:
        caller_file = _inspect.stack()[1].filename
        candidate = Path(caller_file).resolve().parent / f"{figure_name}.svg"
        if candidate.is_file():
            figure_path = candidate

    COMPONENTS[name] = definition
    _PROJECT_COMPONENTS.add(name)
    if figure_path is not None:
        _EXTERNAL_FIGURES[figure_name] = figure_path
