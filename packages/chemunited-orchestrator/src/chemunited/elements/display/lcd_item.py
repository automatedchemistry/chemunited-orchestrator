"""LcdDisplayItem — a black LCD readout on the platform drawing."""

from __future__ import annotations

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PyQt5.QtWidgets import QGraphicsItem, QGraphicsObject

from .model import LcdDisplay

LCD_WIDTH = 132.0
LCD_HEIGHT = 52.0
LCD_BODY_COLOR = QColor("#000000")
LCD_TEXT_COLOR = QColor("#39FF6A")
_SELECTED_COLOR = QColor("#1E88E5")
_NO_VALUE = "--"


def _font(pixel_size: int, *, monospace: bool = False) -> QFont:
    font = QFont()
    if monospace:
        font.setStyleHint(QFont.TypeWriter)
        font.setFamily("Consolas")
        font.setBold(True)
    font.setPixelSize(pixel_size)
    return font


class LcdDisplayItem(QGraphicsObject):
    """A black LCD showing its name and a value.

    The dashboard's live view draws the latest monitoring reading of the bound
    variable in its place; the platform SVG export leaves the item out. In the
    desktop app it always reads "--": it shows no live values here.
    """

    def __init__(self, display: LcdDisplay) -> None:
        super().__init__()
        self._display = display
        self.setFlag(QGraphicsItem.ItemIsMovable, True)  # type: ignore[attr-defined]
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)  # type: ignore[attr-defined]
        self.setPos(*display.position)
        self._update_tool_tip()

    @property
    def name(self) -> str:
        return self._display.name

    @property
    def display(self) -> LcdDisplay:
        """The LCD's binding, at the item's current position."""
        pos = self.pos()
        return self._display.model_copy(
            update={"position": (float(pos.x()), float(pos.y()))}
        )

    def set_display(self, display: LcdDisplay) -> None:
        self._display = display
        self.setPos(*display.position)
        self._update_tool_tip()
        self.update()

    def _update_tool_tip(self) -> None:
        display = self._display
        params = ", ".join(f"{key}={value}" for key, value in display.kwargs.items())
        variable = f"{display.command}({params})" if params else display.command
        self.setToolTip(f"{display.name}\n{display.component} → {variable}")

    def boundingRect(self) -> QRectF:
        return QRectF(-LCD_WIDTH / 2, -LCD_HEIGHT / 2, LCD_WIDTH, LCD_HEIGHT)

    def paint(self, painter, option, widget=None) -> None:
        rect = self.boundingRect().adjusted(1, 1, -1, -1)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(
            QPen(_SELECTED_COLOR, 2) if self.isSelected() else Qt.NoPen  # type: ignore[attr-defined]
        )
        painter.setBrush(LCD_BODY_COLOR)
        painter.drawRoundedRect(rect, 6, 6)

        painter.setPen(LCD_TEXT_COLOR)
        name_font = _font(10)
        painter.setFont(name_font)
        name_rect = rect.adjusted(8, 4, -8, 0)
        name = QFontMetricsF(name_font).elidedText(
            self._display.name, Qt.ElideRight, name_rect.width()  # type: ignore[attr-defined]
        )
        painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignTop, name)  # type: ignore[attr-defined]

        painter.setFont(_font(22, monospace=True))
        painter.drawText(
            rect.adjusted(8, 14, -8, -2), Qt.AlignCenter, _NO_VALUE  # type: ignore[attr-defined]
        )
