from typing import ClassVar

from chemunited_core.figure_registry import SolenoidValve2WayData, SolenoidValveData

from chemunited.elements.component.component_parts import StatusOverlay
from chemunited.elements.component.graph_item import GraphComponent


class _SolenoidValveVisuals:
    """Shared open/closed rendering for solenoid valve figures.

    Reuses the generic status overlay every GraphComponent already builds
    (see graph_item.py:290) rather than a dedicated asset — unlike
    SyringePump's activity tint, this overlay stays visible at all times
    since open/closed is the component's primary state, not a transient
    activity signal.
    """

    def sync_visuals(self) -> None:
        opened = bool(self._data.opened)
        self._overlay.set_status(
            StatusOverlay.COLOR_ACTIVE if opened else StatusOverlay.COLOR_ERROR
        )
        self._overlay.setVisible(True)


class SolenoidValve(_SolenoidValveVisuals, GraphComponent[SolenoidValveData]):
    FIGURE: ClassVar[str] = "SolenoidValve"


class SolenoidValve2Way(_SolenoidValveVisuals, GraphComponent[SolenoidValve2WayData]):
    FIGURE: ClassVar[str] = "SolenoidValve2Way"
