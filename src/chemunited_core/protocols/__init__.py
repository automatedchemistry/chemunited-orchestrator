from typing import cast

from .analytics import (
    HPLCControlProtocols,
    IRControlProtocols,
    MSControlProtocols,
    NMRControlProtocols,
)
from .assembly import (
    Gantry1DProtocols,
    Gantry3DProtocols,
)
from .models import CommandSignature, ComponentProtocol
from .pumps import HPLCPumpProtocols, SyringePumpProtocols
from .sensors import (
    MFCComponentProtocols,
    PhidgetBubbleSensorComponentProtocols,
    PhotoSensorProtocols,
    PressureControlProtocols,
    PressureSensorProtocols,
)
from .technical import (
    HeiConnectTemperatureControlProtocols,
    LengthControlProtocols,
    MultiChannelADCProtocols,
    MultiChannelDACProtocols,
    MultiChannelRelayProtocols,
    PeltierCoolerTemperatureControlProtocols,
    PhotoReactorProtocols,
    StirringControlProtocols,
    TemperatureControlProtocols,
)
from .valves import (
    FourPortDistributionValveProtocols,
    FourPortFivePositionValveProtocols,
    SixPortDistributionValveProtocols,
    SixPortTwoPositionValveProtocols,
    SixteenPortDistributionValveProtocols,
    SolenoidValve2WayProtocols,
    ThreePortFourPositionValveProtocols,
    ThreePortTwoPositionValveProtocols,
    TwelvePortDistributionValveProtocols,
    TwoPortDistributionValveProtocols,
)

_PROJECT_PROTOCOLS: dict[str, type[ComponentProtocol]] = {}


def register_protocol(
    figure: str,
    protocol_cls: type[ComponentProtocol],
    *,
    override: bool = False,
) -> None:
    """Register a ComponentProtocol subclass for a custom component figure.

    Intended for project-local custom components declaring their own
    commands (see chemunited_core.figure_registry.register_component).
    Raises ValueError if *figure* is already registered, unless *override*
    is set.
    """
    if figure in _PROJECT_PROTOCOLS and not override:
        raise ValueError(
            f"Protocol for '{figure}' is already registered. "
            "Pass override=True to replace it."
        )
    _PROJECT_PROTOCOLS[figure] = protocol_cls


def clear_project_protocols() -> None:
    """Remove all project-registered protocols (see register_protocol()).

    Call this at the start of each project load so switching projects
    doesn't leak a previous project's custom protocols into the new one.
    """
    _PROJECT_PROTOCOLS.clear()


def get_protocol_class(figure: str) -> type[ComponentProtocol]:
    """Return the ComponentProtocol subclass to use for *figure*.

    Checks project-registered protocols first, then falls back to a
    built-in ``<figure>Protocols`` class in this package, then to the
    generic ComponentProtocol.
    """
    if figure in _PROJECT_PROTOCOLS:
        return _PROJECT_PROTOCOLS[figure]
    return cast(
        "type[ComponentProtocol]",
        globals().get(f"{figure}Protocols", ComponentProtocol),
    )


__all__ = [
    "ComponentProtocol",
    "CommandSignature",
    "register_protocol",
    "get_protocol_class",
    "clear_project_protocols",
    "HPLCControlProtocols",
    "MSControlProtocols",
    "NMRControlProtocols",
    "IRControlProtocols",
    "Gantry1DProtocols",
    "Gantry3DProtocols",
    "TemperatureControlProtocols",
    "PeltierCoolerTemperatureControlProtocols",
    "LengthControlProtocols",
    "MultiChannelADCProtocols",
    "MultiChannelDACProtocols",
    "MultiChannelRelayProtocols",
    "PhotoReactorProtocols",
    "HPLCPumpProtocols",
    "SyringePumpProtocols",
    "TwoPortDistributionValveProtocols",
    "FourPortDistributionValveProtocols",
    "SixPortDistributionValveProtocols",
    "TwelvePortDistributionValveProtocols",
    "SixteenPortDistributionValveProtocols",
    "ThreePortTwoPositionValveProtocols",
    "ThreePortFourPositionValveProtocols",
    "FourPortFivePositionValveProtocols",
    "SixPortTwoPositionValveProtocols",
    "SolenoidValve2WayProtocols",
    "PhidgetBubbleSensorComponentProtocols",
    "MFCComponentProtocols",
    "PhotoSensorProtocols",
    "PressureSensorProtocols",
    "PressureControlProtocols",
    "StirringControlProtocols",
    "HeiConnectTemperatureControlProtocols",
]
