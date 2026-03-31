from typing import Callable

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainterPath, QPen
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGraphicsItem,
    QGraphicsItemGroup,
    QGraphicsPathItem,
    QGraphicsProxyWidget,
    QGraphicsTextItem,
)
from qfluentwidgets import IndeterminateProgressBar, isDarkTheme

from chemunited.shared.enums.protocols_enum import ProtocolBlock
from chemunited.shared.icon import OrchestratorIcon

from .access_point import WorkflowAccessPoints
from .style import WorkflowColorStyle


class WorkflowSvgIconItem(QGraphicsItem):
    """Render workflow block icons from SVG resources so they stay crisp on zoom."""

    def __init__(self, icon: OrchestratorIcon, size: int):
        super().__init__()
        self._icon = icon
        self._size = size
        self._icon_path = ""
        self._renderer = QSvgRenderer()
        self._update_renderer()

    def _update_renderer(self):
        icon_path = self._icon.path()
        if icon_path != self._icon_path:
            self._icon_path = icon_path
            self._renderer.load(icon_path)

    def boundingRect(self):
        return QRectF(0, 0, self._size, self._size)

    def paint(self, painter, option, widget=None):
        self._update_renderer()
        self._renderer.render(painter, self.boundingRect())


class WorkflowNode(QGraphicsItemGroup):
    def __init__(
        self,
        node_name: str,
        block_tag: ProtocolBlock,
        title: str,
        subtitle: str = "",
        ports_numbers: int = 1,
        protected: bool = False,
        on_position_changed: Callable[["WorkflowNode"], None] | None = None,
    ):
        super().__init__()
        self.node_name = node_name
        self.block_tag = block_tag
        self.title = title
        self.subtitle = subtitle
        self.ports_numbers = max(1, ports_numbers)
        self.protected = protected
        self.shadow_effect: QGraphicsDropShadowEffect | None = None
        self._body_width = 0
        self._body_height = 0
        self.block_icon = self._icon_for_block()
        self._on_position_changed = on_position_changed
        self._suspend_position_callback = False

        self.setFlags(
            QGraphicsItemGroup.ItemIsMovable  # type: ignore[attr-defined]
            | QGraphicsItemGroup.ItemIsSelectable  # type: ignore[attr-defined]
            | QGraphicsItemGroup.ItemSendsGeometryChanges  # type: ignore[attr-defined]
        )

        self.body = QGraphicsPathItem()
        self.icon_item: WorkflowSvgIconItem | None = None
        self.title_item = QGraphicsTextItem()
        self.subtitle_item = QGraphicsTextItem()
        self.progress_proxy: QGraphicsProxyWidget | None = None
        self.progress_bar: IndeterminateProgressBar | None = None
        self.input_ports: WorkflowAccessPoints | None = None
        self.output_ports: WorkflowAccessPoints | None = None
        self.top_ports: WorkflowAccessPoints | None = None
        self.bottom_ports: WorkflowAccessPoints | None = None

        self._build()

    def _palette(self) -> dict[str, QColor]:
        return {
            "body": WorkflowColorStyle.solid(),
            "border": WorkflowColorStyle.contour(),
            "text": WorkflowColorStyle.evidence(),
            "accent": {
                ProtocolBlock.SCRIPT: QColor("#3A7AFE"),
                ProtocolBlock.START: QColor("#1B8F5A"),
                ProtocolBlock.END: QColor("#C0392B"),
                ProtocolBlock.LOOP: QColor("#1B8F5A"),
                ProtocolBlock.IF: QColor("#C98200"),
            }[self.block_tag],
        }

    def _icon_for_block(self) -> OrchestratorIcon:
        return {
            ProtocolBlock.SCRIPT: OrchestratorIcon.PYTHON,
            ProtocolBlock.LOOP: OrchestratorIcon.LOOP,
            ProtocolBlock.IF: OrchestratorIcon.IF,
            ProtocolBlock.START: OrchestratorIcon.PLAY,
            ProtocolBlock.END: OrchestratorIcon.STOP,
        }[self.block_tag]

    def _apply_body_style(self, selected: bool = False):
        palette = self._palette()
        border = QColor("#3A7AFE") if selected else palette["border"]
        self.body.setPen(QPen(border, 2 if selected else 1.4))

    def _body_path(self, width: int, height: int) -> QPainterPath:
        path = QPainterPath()
        if self.block_tag in {ProtocolBlock.START, ProtocolBlock.END}:
            path.addEllipse(0, 0, width, height)
            return path

        if self.block_tag == ProtocolBlock.SCRIPT:
            path.addRoundedRect(0, 0, width, height, 14, 14)
            return path

        if self.block_tag == ProtocolBlock.LOOP:
            path.moveTo(18, 0)
            path.lineTo(width - 18, 0)
            path.lineTo(width, height / 2)
            path.lineTo(width - 18, height)
            path.lineTo(18, height)
            path.lineTo(0, height / 2)
            path.closeSubpath()
            return path

        path.moveTo(width / 2, 0)
        path.lineTo(width, height / 2)
        path.lineTo(width / 2, height)
        path.lineTo(0, height / 2)
        path.closeSubpath()
        return path

    @staticmethod
    def _elide_text(text: str, font: QFont, max_width: int) -> str:
        return QFontMetrics(font).elidedText(
            text,
            Qt.ElideRight,  # type: ignore[attr-defined]
            max_width,
        )

    def _build_progress_bar(self, width: int):
        if self.is_terminal:
            return
        self.progress_bar = IndeterminateProgressBar()
        self.progress_bar.setFixedWidth(max(64, width - 28))
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.stop()
        self.progress_proxy = QGraphicsProxyWidget(self)
        self.progress_proxy.setWidget(self.progress_bar)
        self.progress_proxy.setVisible(False)

    def _build(self):
        palette = self._palette()
        if self.block_tag == ProtocolBlock.SCRIPT:
            width, height = 220, 122
        elif self.block_tag in {ProtocolBlock.START, ProtocolBlock.END}:
            width, height = 96, 96
        else:
            width, height = 200, 114
        self._body_width = width
        self._body_height = height

        self.body.setPath(self._body_path(width, height))
        self.body.setBrush(palette["body"])
        self._apply_body_style()

        self.shadow_effect = QGraphicsDropShadowEffect()
        self.shadow_effect.setBlurRadius(24)
        self.shadow_effect.setOffset(0, 8)
        self.shadow_effect.setColor(QColor(0, 0, 0, 150 if isDarkTheme() else 70))
        self.body.setGraphicsEffect(self.shadow_effect)

        icon_size = 20 if self.is_terminal else 22
        self.icon_item = WorkflowSvgIconItem(self.block_icon, icon_size)

        title_font = QFont("Segoe UI", 10)
        title_font.setBold(True)
        self.title_item.setFont(title_font)
        self.title_item.setDefaultTextColor(palette["text"])

        subtitle_font = QFont("Segoe UI", 8)
        self.subtitle_item.setFont(subtitle_font)
        self.subtitle_item.setDefaultTextColor(palette["accent"])
        self.subtitle_item.setPlainText(self.subtitle)

        if self.is_terminal:
            self.title_item.setPlainText(
                self._elide_text(self.title, title_font, width - 18)
            )
            title_rect = self.title_item.boundingRect()
            if self.icon_item:
                self.icon_item.setPos(
                    (width - self.icon_item.boundingRect().width()) / 2,
                    14,
                )
            self.title_item.setPos((width - title_rect.width()) / 2, 46)
            self.subtitle_item.setPos(
                (width - self.subtitle_item.boundingRect().width()) / 2,
                66,
            )
        else:
            display_title = self._elide_text(self.title, title_font, width - 32)
            self.title_item.setPlainText(display_title)
            title_rect = self.title_item.boundingRect()
            subtitle_rect = self.subtitle_item.boundingRect()
            if self.icon_item:
                self.icon_item.setPos(14, 12)
            text_group_height = title_rect.height() + 4 + subtitle_rect.height()
            group_top = (height - text_group_height) / 2 - 6
            self.title_item.setPos((width - title_rect.width()) / 2, group_top)
            self.subtitle_item.setPos(
                (width - subtitle_rect.width()) / 2,
                group_top + title_rect.height() + 4,
            )
            self.body.setToolTip(self.node_name)

            self._build_progress_bar(width)
            if self.progress_proxy:
                self.progress_proxy.setPos(14, height - 18)

        if self.is_terminal:
            self.body.setToolTip(self.title)

        if self.block_tag != ProtocolBlock.START:
            self.input_ports = WorkflowAccessPoints(
                count=self.ports_numbers, role="left", node=self
            )
        if self.block_tag not in {ProtocolBlock.IF, ProtocolBlock.END}:
            self.output_ports = WorkflowAccessPoints(role="right", node=self)
        if self.block_tag in {ProtocolBlock.LOOP, ProtocolBlock.IF}:
            self.top_ports = WorkflowAccessPoints(
                orientation="horizontal", role="top", node=self
            )
            self.bottom_ports = WorkflowAccessPoints(
                orientation="horizontal", role="bottom", node=self
            )
        self._layout_ports()

        self.addToGroup(self.body)
        if self.icon_item:
            self.addToGroup(self.icon_item)
        self.addToGroup(self.title_item)
        self.addToGroup(self.subtitle_item)
        if self.progress_proxy:
            self.addToGroup(self.progress_proxy)
        if self.input_ports:
            self.addToGroup(self.input_ports)
        if self.output_ports:
            self.addToGroup(self.output_ports)
        if self.top_ports:
            self.addToGroup(self.top_ports)
        if self.bottom_ports:
            self.addToGroup(self.bottom_ports)

    def _layout_ports(self):
        if self.input_ports:
            self.input_ports.setPos(
                -20,
                self._body_height / 2 - self.input_ports.boundingRect().height() / 2,
            )
        if self.output_ports:
            self.output_ports.setPos(
                self._body_width + 5,
                self._body_height / 2 - self.output_ports.boundingRect().height() / 2,
            )
        if self.top_ports:
            self.top_ports.setPos(
                self._body_width / 2 - self.top_ports.boundingRect().width() / 2,
                -20,
            )
        if self.bottom_ports:
            self.bottom_ports.setPos(
                self._body_width / 2 - self.bottom_ports.boundingRect().width() / 2,
                self._body_height + 5,
            )

    def set_input_port_count(self, count: int):
        if self.input_ports is None:
            return
        self.input_ports.set_count(count)
        self._layout_ports()

    def sync_position(self, pos: tuple[float, float]) -> None:
        self._suspend_position_callback = True
        try:
            self.setPos(QPointF(*pos))
        finally:
            self._suspend_position_callback = False

    @property
    def is_terminal(self) -> bool:
        return self.block_tag in {ProtocolBlock.START, ProtocolBlock.END}

    @property
    def is_protected(self) -> bool:
        return self.protected

    def start_progress(self):
        if self.progress_bar is None or self.progress_proxy is None:
            return
        self.progress_proxy.setVisible(True)
        self.progress_bar.start()

    def stop_progress(self):
        if self.progress_bar is None or self.progress_proxy is None:
            return
        self.progress_bar.stop()
        self.progress_proxy.setVisible(False)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._apply_body_style(bool(value))
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and self.scene() is not None
            and not self._suspend_position_callback
            and self._on_position_changed is not None
        ):
            self._on_position_changed(self)
        return super().itemChange(change, value)
