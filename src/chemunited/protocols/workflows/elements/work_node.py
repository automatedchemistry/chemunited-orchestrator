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
from qfluentwidgets import isDarkTheme

from chemunited.shared.enums.protocols_enum import ProtocolBlock
from chemunited.shared.icon import OrchestratorIcon

from .access_point import WorkflowAccessPoints
from .status_bar import WorkflowStatusBar
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
        label: str = "",
        description: str = "",
        ports_numbers: int = 1,
        protected: bool = False,
        on_position_changed: Callable[["WorkflowNode"], None] | None = None,
    ):
        super().__init__()
        self.node_name = node_name
        self.block_tag = block_tag
        self.title = title
        self.subtitle = subtitle
        self.label = label or node_name
        self.description = description
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
        self.description_item = QGraphicsTextItem()
        self.progress_proxy: QGraphicsProxyWidget | None = None
        self.progress_bar: WorkflowStatusBar | None = None
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
                ProtocolBlock.COMMAND: QColor("#D16946"),
            }[self.block_tag],
        }

    def _icon_for_block(self) -> OrchestratorIcon:
        return {
            ProtocolBlock.SCRIPT: OrchestratorIcon.PYTHON,
            ProtocolBlock.LOOP: OrchestratorIcon.LOOP,
            ProtocolBlock.IF: OrchestratorIcon.IF,
            ProtocolBlock.START: OrchestratorIcon.PLAY,
            ProtocolBlock.END: OrchestratorIcon.STOP,
            ProtocolBlock.COMMAND: OrchestratorIcon.PROCESS,
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

        if self.block_tag == ProtocolBlock.LOOP:
            path.moveTo(18, 0)
            path.lineTo(width - 18, 0)
            path.lineTo(width, height / 2)
            path.lineTo(width - 18, height)
            path.lineTo(18, height)
            path.lineTo(0, height / 2)
            path.closeSubpath()
            return path

        if self.block_tag == ProtocolBlock.IF:
            path.moveTo(width / 2, 0)
            path.lineTo(width, height / 2)
            path.lineTo(width / 2, height)
            path.lineTo(0, height / 2)
            path.closeSubpath()
            return path

        path.addRoundedRect(0, 0, width, height, 14, 14)
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
        self.progress_bar = WorkflowStatusBar(max(64, width - 28))
        self.progress_proxy = QGraphicsProxyWidget(self)
        self.progress_proxy.setWidget(self.progress_bar)
        self.progress_proxy.setZValue(20)
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

        description_font = QFont("Segoe UI", 8)
        self.description_item.setFont(description_font)
        self.description_item.setDefaultTextColor(palette["text"])

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
            display_description = self._elide_text(
                self.description,
                description_font,
                width - 28,
            )
            self.title_item.setPlainText(display_title)
            self.description_item.setPlainText(display_description)
            title_rect = self.title_item.boundingRect()
            subtitle_rect = self.subtitle_item.boundingRect()
            description_rect = self.description_item.boundingRect()
            if self.icon_item:
                self.icon_item.setPos(14, 12)
            text_group_height = (
                title_rect.height()
                + 3
                + subtitle_rect.height()
                + 3
                + description_rect.height()
            )
            group_top = (height - text_group_height) / 2 - 8
            self.title_item.setPos((width - title_rect.width()) / 2, group_top)
            self.subtitle_item.setPos(
                (width - subtitle_rect.width()) / 2,
                group_top + title_rect.height() + 3,
            )
            self.description_item.setPos(
                (width - description_rect.width()) / 2,
                group_top + title_rect.height() + subtitle_rect.height() + 6,
            )
            self._update_tooltip()

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
        self.addToGroup(self.description_item)
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

    def update_metadata(
        self,
        title: str,
        label: str,
        description: str,
    ) -> None:
        if self.is_terminal:
            return
        self.title = title
        self.label = label
        self.description = description

        title_font = self.title_item.font()
        description_font = self.description_item.font()
        self.title_item.setPlainText(
            self._elide_text(title, title_font, self._body_width - 32)
        )
        self.description_item.setPlainText(
            self._elide_text(
                description,
                description_font,
                self._body_width - 28,
            )
        )

        title_rect = self.title_item.boundingRect()
        subtitle_rect = self.subtitle_item.boundingRect()
        description_rect = self.description_item.boundingRect()
        text_group_height = (
            title_rect.height()
            + 3
            + subtitle_rect.height()
            + 3
            + description_rect.height()
        )
        group_top = (self._body_height - text_group_height) / 2 - 8
        self.title_item.setPos(
            (self._body_width - title_rect.width()) / 2,
            group_top,
        )
        self.subtitle_item.setPos(
            (self._body_width - subtitle_rect.width()) / 2,
            group_top + title_rect.height() + 3,
        )
        self.description_item.setPos(
            (self._body_width - description_rect.width()) / 2,
            group_top + title_rect.height() + subtitle_rect.height() + 6,
        )
        self._update_tooltip()
        self.update()

    def _update_tooltip(self) -> None:
        self.body.setToolTip(
            f"Label: {self.label}\n"
            f"Node ID: {self.node_name}\n"
            f"Description: {self.description}"
        )

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

    def set_status(self, status) -> None:
        if self.progress_bar is None or self.progress_proxy is None:
            return
        visible = self.progress_bar.set_status(status)
        self.progress_bar.setVisible(visible)
        self.progress_proxy.setVisible(visible)
        self.progress_bar.update()
        self.progress_proxy.update()
        self.update()

        scene = self.scene()
        if scene is None:
            return
        scene.update(self.sceneBoundingRect())
        for view in scene.views():
            view.viewport().update()

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
