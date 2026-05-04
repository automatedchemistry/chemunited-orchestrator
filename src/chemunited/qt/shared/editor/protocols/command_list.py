from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from PyQt5.QtCore import QMimeData, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QDrag, QIcon
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import TreeWidget, isDarkTheme

import chemunited.qt.elements.component.protocols as protocol_module
from chemunited.qt.elements.component.protocols.models import (
    CommandSignature,
    ComponentProtocol,
)
from chemunited.qt.shared.icon import OrchestratorIcon

QT_COPY_ACTION = getattr(Qt, "CopyAction")
QT_DISPLAY_ROLE = getattr(Qt, "DisplayRole")
QT_ITEM_IS_DRAG_ENABLED = getattr(Qt, "ItemIsDragEnabled")
QT_ITEM_IS_ENABLED = getattr(Qt, "ItemIsEnabled")
QT_ITEM_IS_SELECTABLE = getattr(Qt, "ItemIsSelectable")


def _humanize(text: str) -> str:
    return text.replace("_", " ").strip().title()


def _protocol_name_candidates(figure: str) -> list[str]:
    return [f"{figure}Protocols"]


def get_protocol_by_figure(
    figure: str,
    component_name: str | None = None,
) -> ComponentProtocol:
    for candidate in _protocol_name_candidates(figure):
        protocol_cls = getattr(protocol_module, candidate, None)
        if (
            isinstance(protocol_cls, type)
            and issubclass(protocol_cls, ComponentProtocol)
            and protocol_cls is not ComponentProtocol
        ):
            return protocol_cls(component_name or figure)

    raise AttributeError(f"Protocol {figure}Protocols not found")


@dataclass(slots=True)
class _ProtocolSource:
    component_name: str
    figure: str
    protocol: ComponentProtocol


class _CommandCard(QFrame):
    def __init__(
        self,
        title: str,
        method: str,
        subtitle: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        method_color = "#2d7dff" if method.upper() == "GET" else "#1a8f5a"
        title_color = "#f3f3f3" if isDarkTheme() else "#202020"
        subdued = (
            "rgba(255, 255, 255, 0.62)" if isDarkTheme() else "rgba(0, 0, 0, 0.56)"
        )

        self.setObjectName("commandCard")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # type: ignore[attr-defined]
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(56)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(4)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)

        self.titleLabel = QLabel(title, self)
        self.titleLabel.setObjectName("commandTitle")
        self.titleLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # type: ignore[attr-defined]
        self.titleLabel.setStyleSheet(
            f"font-size: 13px; font-weight: 600; color: {title_color}; background: transparent;"
        )
        header.addWidget(self.titleLabel)
        header.addStretch()

        self.methodLabel = QLabel(method.upper(), self)
        self.methodLabel.setObjectName("commandMethod")
        self.methodLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # type: ignore[attr-defined]
        self.methodLabel.setStyleSheet(
            f"background: {method_color};"
            f"border: 1px solid {method_color};"
            "border-radius: 6px;"
            "color: white;"
            "font-size: 10px;"
            "font-weight: 700;"
            "padding: 2px 8px;"
        )
        header.addWidget(self.methodLabel)

        self.subtitleLabel = QLabel(subtitle, self)
        self.subtitleLabel.setObjectName("commandSubtitle")
        self.subtitleLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # type: ignore[attr-defined]
        self.subtitleLabel.setStyleSheet(
            f"font-size: 11px; color: {subdued}; background: transparent;"
        )

        root.addLayout(header)
        root.addWidget(self.subtitleLabel)


class _ComponentCard(QFrame):
    def __init__(
        self,
        component_name: str,
        figure: str,
        protocol_name: str,
        command_count: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        title_color = "#f3f3f3" if isDarkTheme() else "#202020"
        subdued = (
            "rgba(255, 255, 255, 0.62)" if isDarkTheme() else "rgba(0, 0, 0, 0.56)"
        )
        self.setObjectName("componentCard")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # type: ignore[attr-defined]
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(62)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(10)

        self.iconLabel = QLabel(self)
        self.iconLabel.setFixedSize(28, 28)
        self.iconLabel.setPixmap(
            QIcon(OrchestratorIcon.COMPONENT_ICON.path()).pixmap(22, 22)
        )
        self.iconLabel.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        self.iconLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # type: ignore[attr-defined]
        self.iconLabel.setStyleSheet("background: transparent;")
        root.addWidget(self.iconLabel, alignment=Qt.AlignTop)  # type: ignore[attr-defined]

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(3)

        self.titleLabel = QLabel(component_name, self)
        self.titleLabel.setObjectName("componentTitle")
        self.titleLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # type: ignore[attr-defined]
        self.titleLabel.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {title_color}; background: transparent;"
        )
        text_layout.addWidget(self.titleLabel)

        summary = f"{figure} | {protocol_name} | {command_count} commands"
        self.summaryLabel = QLabel(summary, self)
        self.summaryLabel.setObjectName("componentSummary")
        self.summaryLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # type: ignore[attr-defined]
        self.summaryLabel.setStyleSheet(
            f"font-size: 11px; color: {subdued}; background: transparent;"
        )
        text_layout.addWidget(self.summaryLabel)

        root.addLayout(text_layout, stretch=1)


class CommandList(TreeWidget):
    ROLE_KIND = Qt.UserRole + 1  # type: ignore[attr-defined]
    ROLE_LINE_SCRIPT = Qt.UserRole + 2  # type: ignore[attr-defined]
    MIME = "application/x-chemunited-command"

    command_activated = pyqtSignal(str)
    snippet_activated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_ref = parent

        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setAnimated(True)
        self.setIndentation(12)
        self.setUniformRowHeights(False)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(QT_COPY_ACTION)
        self.setExpandsOnDoubleClick(True)
        self.itemDoubleClicked.connect(self._on_item_double_clicked)

        self.sync_protocols()

    def _sources_from_parent(self) -> list[_ProtocolSource]:
        orchestrator = getattr(self.parent_ref, "orchestrator", None)
        components = getattr(orchestrator, "components", None)
        if components is None:
            return []

        sources: list[_ProtocolSource] = []
        for component_name, manager in components.items():
            protocol = getattr(manager, "protocols", None)
            if not isinstance(protocol, ComponentProtocol) or not protocol.commands:
                continue

            figure = str(
                getattr(getattr(manager, "inf", None), "figure", component_name)
            )
            sources.append(
                _ProtocolSource(
                    component_name=str(component_name),
                    figure=figure,
                    protocol=protocol,
                )
            )

        return sources

    def _sources_from_figures(
        self,
        components_figures: list[str] | None,
    ) -> list[_ProtocolSource]:
        sources: list[_ProtocolSource] = []
        for figure in components_figures or []:
            protocol = get_protocol_by_figure(figure, component_name=figure)
            sources.append(
                _ProtocolSource(
                    component_name=figure,
                    figure=figure,
                    protocol=protocol,
                )
            )
        return sources

    def sync_protocols(self, components_figures: list[str] | None = None):
        self.clear()

        sources = self._sources_from_parent()
        if not sources:
            sources = self._sources_from_figures(components_figures)

        total_commands = 0

        for source in sources:
            command_entries: list[
                tuple[str, type[CommandSignature], CommandSignature]
            ] = []
            for command_key, command_class in source.protocol.commands.items():
                try:
                    command_instance = command_class(component=source.component_name)
                except Exception as exc:
                    logger.opt(exception=exc).warning(
                        "Could not build default command instance "
                        f"{command_class.__name__!r} for {source.component_name!r}"
                    )
                    continue
                command_entries.append((command_key, command_class, command_instance))

            if not command_entries:
                continue

            component_item = QTreeWidgetItem(self)
            component_item.setText(0, "")
            component_item.setData(0, self.ROLE_KIND, "component")
            component_item.setToolTip(
                0,
                f"{source.component_name}\nFigure: {source.figure}",
            )
            component_item.setFlags(QT_ITEM_IS_ENABLED)
            component_item.setExpanded(True)
            component_item.setSizeHint(0, QSize(320, 68))
            self.setItemWidget(
                component_item,
                0,
                _ComponentCard(
                    component_name=source.component_name,
                    figure=source.figure,
                    protocol_name=type(source.protocol).__name__,
                    command_count=len(command_entries),
                    parent=self,
                ),
            )

            for command_key, _command_class, command_instance in command_entries:
                line_script = command_instance.line_script
                subtitle = (
                    f"{source.component_name} | {command_instance.method} | "
                    f"{len(command_instance.parameters)} parameter(s)"
                )
                item = QTreeWidgetItem(component_item)
                item.setData(0, QT_DISPLAY_ROLE, "")
                item.setData(0, self.ROLE_KIND, "command")
                item.setData(0, self.ROLE_LINE_SCRIPT, line_script)
                item.setToolTip(0, line_script)
                item.setFlags(
                    QT_ITEM_IS_ENABLED | QT_ITEM_IS_SELECTABLE | QT_ITEM_IS_DRAG_ENABLED
                )
                item.setSizeHint(0, QSize(300, 82))
                self.setItemWidget(
                    item,
                    0,
                    _CommandCard(
                        title=command_instance.command or command_key,
                        method=command_instance.method,
                        subtitle=subtitle,
                        parent=self,
                    ),
                )
                total_commands += 1

        self.expandAll()
        return total_commands

    def current_line_script(self) -> str | None:
        item = self.currentItem()
        if item is None or item.data(0, self.ROLE_KIND) != "command":
            return None

        line_script = item.data(0, self.ROLE_LINE_SCRIPT)
        if isinstance(line_script, str):
            return line_script
        return None

    def current_snippet(self) -> str | None:
        return self.current_line_script()

    def mimeTypes(self) -> list[str]:
        return [self.MIME, "text/plain"]

    def mimeData(self, items: list[QTreeWidgetItem]) -> QMimeData | None:
        command_item = next(
            (item for item in items if item.data(0, self.ROLE_KIND) == "command"),
            None,
        )
        if command_item is None:
            return None

        line_script = command_item.data(0, self.ROLE_LINE_SCRIPT)
        if not isinstance(line_script, str):
            return None

        mime_data = QMimeData()
        mime_data.setData(self.MIME, line_script.encode("utf-8"))
        mime_data.setText(line_script)
        return mime_data

    def startDrag(self, supportedActions) -> None:
        item = self.currentItem()
        if item is None or item.data(0, self.ROLE_KIND) != "command":
            return

        mime_data = self.mimeData([item])
        if mime_data is None:
            return

        drag = QDrag(self)
        drag.setMimeData(mime_data)

        card = self.itemWidget(item, 0)
        if card is not None:
            pixmap = card.grab()
        else:
            pixmap = self.viewport().grab(self.visualItemRect(item))

        if not pixmap.isNull():
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())

        drag.exec_(QT_COPY_ACTION)

    def _on_item_double_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        if item.data(0, self.ROLE_KIND) != "command":
            return

        line_script = item.data(0, self.ROLE_LINE_SCRIPT)
        if not isinstance(line_script, str):
            return

        self.command_activated.emit(line_script)
        self.snippet_activated.emit(line_script)


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    command_list = CommandList()
    command_list.sync_protocols(
        components_figures=["SyringePump", "SixPortTwoPositionValve"]
    )
    command_list.snippet_activated.connect(print)
    command_list.show()
    sys.exit(app.exec_())
