from typing import TYPE_CHECKING, ClassVar, cast

from chemunited_core.components import ComponentData
from chemunited_core.components.component import PATTERN_DIMENSION
from chemunited_core.figure_registry import SolenoidValve2WayData, SolenoidValveData
from PyQt5.QtCore import QLineF
from PyQt5.QtGui import QColor

from chemunited.elements.component.component_parts import StatusOverlay
from chemunited.elements.component.graph_item import GraphComponent


class StatusOverlaySolenoid(StatusOverlay):

    COLOR_ACTIVE: QColor = QColor(0, 200, 83, 255)  # green
    COLOR_CLOSED: QColor = QColor(229, 57, 53, 255)  # red
    OPEN_ICON = "line"
    CLOSED_ICON = "cross"

    def __init__(self, dimension: int = PATTERN_DIMENSION, parent=None) -> None:
        super().__init__(dimension=PATTERN_DIMENSION // 4, parent=parent)

    def paint(self, painter, option, widget=None):

        super().paint(painter, option, widget)

        painter.setPen(QColor(255, 255, 255, 255))  # white
        painter.setBrush(QColor(255, 255, 255, 255))  # white
        if self._color == self.COLOR_ACTIVE:
            # draw a small line inside the overlay to indicate the solenoid is open
            painter.drawLine(
                QLineF(
                    self.boundingRect().center().x() - 5,
                    self.boundingRect().center().y(),
                    self.boundingRect().center().x() + 5,
                    self.boundingRect().center().y(),
                )
            )
        elif self._color == self.COLOR_CLOSED:
            # draw a small cross inside the overlay to indicate the solenoid is closed
            painter.drawLine(
                QLineF(
                    self.boundingRect().center().x() - 5,
                    self.boundingRect().center().y() - 5,
                    self.boundingRect().center().x() + 5,
                    self.boundingRect().center().y() + 5,
                )
            )
            painter.drawLine(
                QLineF(
                    self.boundingRect().center().x() - 5,
                    self.boundingRect().center().y() + 5,
                    self.boundingRect().center().x() + 5,
                    self.boundingRect().center().y() - 5,
                )
            )


class StatusOverlaySolenoid2Way(StatusOverlay):

    COLOR_ACTIVE: QColor = QColor(0, 200, 83, 255)  # green
    COLOR_CLOSED: QColor = QColor(255, 152, 0, 255)  # orange

    def __init__(self, dimension: int = PATTERN_DIMENSION, parent=None) -> None:
        super().__init__(dimension=PATTERN_DIMENSION // 4, parent=parent)
        self._opened = False

    def set_opened(self, opened: bool) -> None:
        self._opened = bool(opened)
        self.set_status(self.COLOR_ACTIVE if self._opened else self.COLOR_CLOSED)

    def paint(self, painter, option, widget=None):

        super().paint(painter, option, widget)

        painter.setPen(QColor(255, 255, 255, 255))  # white
        painter.setBrush(QColor(255, 255, 255, 255))  # white
        if self._opened:
            # draw a small horizontal line inside the overlay to indicate the solenoid is open
            painter.drawLine(
                QLineF(
                    self.boundingRect().center().x() - 5,
                    self.boundingRect().center().y(),
                    self.boundingRect().center().x() + 5,
                    self.boundingRect().center().y(),
                )
            )
        else:
            # draw a small vertical line inside the overlay to indicate the solenoid is closed
            print("drawing vertical line for closed solenoid")
            painter.drawLine(
                QLineF(
                    self.boundingRect().center().x(),
                    self.boundingRect().center().y() - 5,
                    self.boundingRect().center().x(),
                    self.boundingRect().center().y() + 5,
                )
            )


if TYPE_CHECKING:
    # Static-typing-only base: gives mypy the real build()/post_layout()/
    # _overlay/_data members to check super() calls and attribute access
    # against. Never used as a real base at runtime — the actual GraphComponent
    # base is supplied by whichever concrete class mixes this in below (see
    # SolenoidValve / SolenoidValve2Way), via ordinary multiple inheritance.
    _SolenoidValveHost = GraphComponent[ComponentData]
else:
    _SolenoidValveHost = object


class _SolenoidValveVisuals(_SolenoidValveHost):
    """Shared open/closed rendering for solenoid valve figures.

    Reuses the generic status overlay every GraphComponent already builds
    (see graph_item.py:290) rather than a dedicated asset — unlike
    SyringePump's activity tint, this overlay stays visible at all times
    since open/closed is the component's primary state, not a transient
    activity signal.
    """

    STATUS_OVERLAY_POS: ClassVar[tuple[float, float] | None] = None

    def build(self) -> None:
        super().build()
        self.sync_visuals()

    def post_layout(self) -> None:
        super().post_layout()
        if self.STATUS_OVERLAY_POS is not None:
            self._overlay.setPos(*self.STATUS_OVERLAY_POS)

    def sync_visuals(self) -> None:
        data = cast("SolenoidValveData | SolenoidValve2WayData", self._data)
        opened = bool(data.opened)
        if data.figure == "SolenoidValve2Way":
            cast(StatusOverlaySolenoid2Way, self._overlay).set_opened(opened)
        else:
            self._overlay.set_status(
                StatusOverlaySolenoid.COLOR_ACTIVE
                if opened
                else StatusOverlaySolenoid.COLOR_CLOSED
            )
        self._overlay.setVisible(True)


class SolenoidValve(_SolenoidValveVisuals, GraphComponent[SolenoidValveData]):
    FIGURE: ClassVar[str] = "SolenoidValve"
    STATUS_OVERLAY: ClassVar[type[StatusOverlaySolenoid]] = StatusOverlaySolenoid
    STATUS_OVERLAY_POS: ClassVar[tuple[float, float] | None] = (
        0,
        -PATTERN_DIMENSION / 7,
    )


class SolenoidValve2Way(_SolenoidValveVisuals, GraphComponent[SolenoidValve2WayData]):
    FIGURE: ClassVar[str] = "SolenoidValve2Way"
    STATUS_OVERLAY: ClassVar[type[StatusOverlaySolenoid2Way]] = (
        StatusOverlaySolenoid2Way
    )
    STATUS_OVERLAY_POS: ClassVar[tuple[float, float] | None] = (
        0,
        PATTERN_DIMENSION / 5,
    )
