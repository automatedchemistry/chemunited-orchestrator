from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QFile, QMimeData, QSize, Qt
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

from chemunited.core.components.enums import ComponentType
from chemunited.qt.elements.component import list_components
from chemunited.qt.shared.icon import OrchestratorIcon

_COMPONENTS_DIR = (
    Path(__file__).resolve().parents[1] / "shared" / "resources" / "components"
)
QT_DISPLAY_ROLE = getattr(Qt, "DisplayRole")
QT_ITEM_IS_DRAG_ENABLED = getattr(Qt, "ItemIsDragEnabled")
QT_ITEM_IS_ENABLED = getattr(Qt, "ItemIsEnabled")
QT_ITEM_IS_SELECTABLE = getattr(Qt, "ItemIsSelectable")


def _humanize(text: str) -> str:
    return text.replace("_", " ").strip().title()


def _description_for(component_type: ComponentType | None) -> str:
    if component_type == ComponentType.ELECTRONIC:
        return "Electronic component"
    if component_type == ComponentType.UTENSIL:
        return "Utensil component"
    return "Component"


def _path_exists(path: str) -> bool:
    if path.startswith(":/"):
        return QFile.exists(path)
    return Path(path).exists()


def _figure_name_candidates(component_name: str) -> list[str]:
    candidates = [component_name]

    if component_name.endswith("Component"):
        candidates.append(f"{component_name[: -len('Component')]}component")

    if component_name:
        candidates.append(f"{component_name[0].lower()}{component_name[1:]}")

    return list(dict.fromkeys(candidates))


def _component_icon(component_name: str) -> QIcon:
    themed_suffix = "DARK" if isDarkTheme() else "LIGHT"

    for figure_name in _figure_name_candidates(component_name):
        resource_path = (
            f":/components_icons/components/{figure_name}{themed_suffix}.svg"
        )
        if _path_exists(resource_path):
            return QIcon(resource_path)

        local_svg = _COMPONENTS_DIR / f"{figure_name}{themed_suffix}.svg"
        if local_svg.exists():
            return QIcon(str(local_svg))

        local_png = _COMPONENTS_DIR / f"{figure_name}{themed_suffix}.png"
        if local_png.exists():
            return QIcon(str(local_png))

    return QIcon(OrchestratorIcon.COMPONENT_ICON.path())


class AppCard(QFrame):
    def __init__(
        self,
        icon: QIcon,
        component: str,
        group: str,
        description: str,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self.setObjectName("appCard")
        self.setAttribute(Qt.WA_StyledBackground, True)  # type: ignore[attr-defined]
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # type: ignore[attr-defined]
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(72)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(10)

        self.iconLabel = QLabel(self)
        self.iconLabel.setObjectName("appCardIcon")
        self.iconLabel.setFixedSize(40, 40)
        self.iconLabel.setAlignment(Qt.AlignCenter)  # type: ignore[attr-defined]
        self.iconLabel.setPixmap(icon.pixmap(36, 36))
        self.iconLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # type: ignore[attr-defined]

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)

        self.titleLabel = QLabel(component, self)
        self.titleLabel.setObjectName("appCardTitle")
        self.titleLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # type: ignore[attr-defined]
        # self.titleLabel.setFont(QFont("", 12, QFont.Bold))

        self.groupLabel = QLabel(group, self)
        self.groupLabel.setObjectName("appCardGroup")
        self.groupLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # type: ignore[attr-defined]
        # self.groupLabel.setFont(QFont("", 10, QFont.Normal))

        self.descriptionLabel = QLabel(description, self)
        self.descriptionLabel.setObjectName("appCardDescription")
        self.descriptionLabel.setWordWrap(True)
        self.descriptionLabel.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # type: ignore[attr-defined]
        # self.descriptionLabel.setFont(QFont("", 10, QFont.Normal))

        text_layout.addWidget(self.titleLabel)
        text_layout.addWidget(self.groupLabel)
        text_layout.addWidget(self.descriptionLabel)

        root.addWidget(self.iconLabel, alignment=Qt.AlignTop)  # type: ignore[attr-defined]
        root.addLayout(text_layout, stretch=1)

        self.setStyleSheet(
            """
            QFrame#appCard {
                background: transparent;
                border: none;
            }
            QLabel#appCardTitle {
                font-size: 13px;
                font-weight: 600;
            }
            QLabel#appCardGroup {
                font-size: 11px;
                color: rgba(120, 120, 120, 0.95);
                text-transform: uppercase;
            }
            QLabel#appCardDescription {
                font-size: 11px;
                color: rgba(120, 120, 120, 0.95);
            }
            """
        )


class TreeAddItem(TreeWidget):
    ROLE_KIND = Qt.UserRole + 1  # type: ignore[attr-defined]
    ROLE_PAYLOAD = Qt.UserRole + 2  # type: ignore[attr-defined]
    MIME = "application/x-chemunited-component"

    def __init__(self, parent=None, icon_size=64):
        super().__init__(parent=parent)
        self._icon_size = QSize(icon_size, icon_size)
        self._categories: dict[str, list[str]] = {}
        self._components: dict[str, type] = {}

        self.setHeaderHidden(True)
        self.setColumnCount(1)
        self.setAnimated(True)
        self.setIconSize(self._icon_size)
        self.setIndentation(12)
        self.setUniformRowHeights(False)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.CopyAction)  # type: ignore[attr-defined]
        self.setExpandsOnDoubleClick(True)

        self.reload_components()

    def reload_components(self) -> None:
        self.clear()
        self._categories, self._components = list_components()

        for category, component_names in self._categories.items():
            category_item = QTreeWidgetItem(self)
            category_item.setText(0, _humanize(category))
            category_item.setData(0, self.ROLE_KIND, "category")
            category_item.setData(0, self.ROLE_PAYLOAD, category)
            category_item.setFlags(QT_ITEM_IS_ENABLED)
            category_item.setExpanded(True)

            for component_name in component_names:
                component_cls = self._components[component_name]
                component_type = getattr(
                    getattr(component_cls, "METADATA", None),
                    "COMPONENT_TYPE",
                    None,
                )
                description = _description_for(component_type)
                card = AppCard(
                    icon=_component_icon(component_name),
                    component=component_name,
                    group=_humanize(category),
                    description=description,
                    parent=self,
                )

                item = QTreeWidgetItem(category_item)
                item.setText(0, "")
                item.setData(0, QT_DISPLAY_ROLE, "")
                item.setData(0, self.ROLE_KIND, "component")
                item.setData(0, self.ROLE_PAYLOAD, f"{category}|{component_name}")
                item.setToolTip(
                    0,
                    f"{component_name}\n{_humanize(category)}\n{description}",
                )
                item.setFlags(
                    QT_ITEM_IS_ENABLED | QT_ITEM_IS_SELECTABLE | QT_ITEM_IS_DRAG_ENABLED
                )
                item.setSizeHint(
                    0,
                    QSize(
                        max(240, self._icon_size.width() + 120),
                        max(72, self._icon_size.height() + 8),
                    ),
                )
                self.setItemWidget(item, 0, card)

        self.expandAll()

    def mimeTypes(self) -> list[str]:
        return [self.MIME]

    def mimeData(self, items: list[QTreeWidgetItem]) -> QMimeData | None:
        component_item = next(
            (item for item in items if item.data(0, self.ROLE_KIND) == "component"),
            None,
        )
        if component_item is None:
            return None

        payload = component_item.data(0, self.ROLE_PAYLOAD)
        if not payload:
            return None

        mime_data = QMimeData()
        mime_data.setData(self.MIME, str(payload).encode("utf-8"))
        mime_data.setText(str(payload))
        return mime_data

    def startDrag(self, supportedActions) -> None:
        item = self.currentItem()
        if item is None or item.data(0, self.ROLE_KIND) != "component":
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

        drag.exec_(Qt.CopyAction)  # type: ignore[attr-defined]


if __name__ == "__main__":
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    tree = TreeAddItem()
    tree.show()
    sys.exit(app.exec_())
