from chemunited.qt.utils.flowchem_listener import FLOWCHEM_SERVERS, access_url
from chemunited.qt.shared.icon import OrchestratorIcon
from qfluentwidgets import (
    ListWidget,
    ComboBox,
    StrongBodyLabel,
    isDarkTheme,
    TransparentToolButton,
    FluentIcon,
    PushButton
)
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QListWidgetItem, QLabel, QHBoxLayout
from PyQt5.QtCore import Qt, QMimeData, QFile
from PyQt5.QtGui import QDrag, QIcon, QPixmap, QPainter, QColor, QFont
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from chemunited.qt.setup import SetupWindow


class OnlineList(ListWidget):
    MIME = "application/x-chemunited-online-list"

    def __init__(self, api_obj, parent=None):
        super().__init__(parent)
        self.api_obj = api_obj
        self.setDragEnabled(True)
        # Important: allow dragging outside the widget
        self.setDefaultDropAction(Qt.MoveAction)  # type:ignore[attr-defined]
    
    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item:
            url_c = self.api_obj.currentText() + "/" + item.text()
            mime = QMimeData()
            mime.setData(self.MIME, url_c.encode("utf-8"))
            mime.setText(url_c)

            drag = QDrag(self)
            drag.setMimeData(mime)

            # === Create a custom pixmap that shows icon + text ===
            icon = item.icon()
            text = item.text()

            # Define pixmap size (width can adapt to text length)
            width = max(140, len(text) * 8 + 40)
            height = 36
            pixmap = QPixmap(width, height)
            pixmap.fill(Qt.transparent)  # type:ignore[attr-defined]

            painter = QPainter(pixmap)

            # Rounded background (light or dark depending on theme)
            bg_color = (
                QColor(40, 40, 40, 180) if isDarkTheme() else QColor(240, 240, 240, 200)
            )
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(bg_color)
            painter.setPen(Qt.NoPen)  # type:ignore[attr-defined]
            painter.drawRoundedRect(0, 0, width, height, 8, 8)

            # Draw icon
            if not icon.isNull():
                icon_pix = icon.pixmap(24, 24)
                painter.drawPixmap(6, (height - 24) // 2, icon_pix)

            # Draw text
            painter.setFont(QFont("Segoe UI", 9))
            painter.setPen(
                Qt.white if isDarkTheme() else Qt.black  # type:ignore[attr-defined]
            )
            painter.drawText(36, 22, text)

            painter.end()

            # Set this custom pixmap as the drag image
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())

            drag.exec_(Qt.CopyAction)  # type:ignore[attr-defined]


class OnlineComponent(QWidget):
    def __init__(self, parent):
        super().__init__()
        self._parent: Optional["SetupWindow"] = parent
        layout = QVBoxLayout(self)

        self.api = ComboBox(self)
        self.api.setPlaceholderText("-")
        self.api.currentTextChanged.connect(self.select_api)
        layout.addWidget(StrongBodyLabel("Available Flowchem servers", parent=self))
        layout.addWidget(self.api)

        self.OnlineList = OnlineList(api_obj=self.api)
        widget = QWidget()
        icon = TransparentToolButton(OrchestratorIcon.MOVE, self)
        icon.setToolTip("Item in the list is movable to the graphic")
        label_text = StrongBodyLabel("Available Online Components", parent=self)
        label_text.setToolTip("Item in the list is movable to the graphic")
        label_layout = QHBoxLayout(widget)
        label_layout.setContentsMargins(0, 0, 0, 0)
        label_layout.addWidget(icon)
        label_layout.addWidget(label_text)
        layout.addWidget(widget)
        layout.addWidget(self.OnlineList)

        self.LockList = ListWidget()
        layout.addWidget(StrongBodyLabel("Lock Online Components", parent=self))
        layout.addWidget(self.LockList)

        update_button = PushButton(OrchestratorIcon.UPDATE, "Update List", self)
        update_button.clicked.connect(self.update_list)
        layout.addWidget(update_button)

    def update_list(self):
        self.api.clear()
        FLOWCHEM_SERVERS.update()
        for item in FLOWCHEM_SERVERS.servers:
            self.api.addItem(item)

    def select_api(self, item):
        # Determine current theme
        _theme = "DARK" if isDarkTheme() else "LIGHT"
        url = self.api.text()
        self.OnlineList.clear()

        if item in FLOWCHEM_SERVERS.servers:
            for device in FLOWCHEM_SERVERS.servers[url]:
                for component in FLOWCHEM_SERVERS.servers[url][device]:
                    urlc = f"{url}/{device}/{component}"
                    status, info = access_url(url=urlc)

                    # Default icon (fallback)
                    figure = OrchestratorIcon.COMPONENT_ICON.path()

                    # Try to find a component-specific icon based on theme
                    for item in info.get("corresponding_class", []):
                        icon_path = (
                            f":/orchestrator/components_icons/{item}{_theme}.png"
                        )
                        # Check if that resource actually exists
                        if QFile.exists(icon_path):
                            figure = icon_path
                            break

                    # Create the list item with icon + text
                    text = f"{device}/{component}"
                    list_item = QListWidgetItem(QIcon(figure), text)
                    self.OnlineList.addItem(list_item)

                    # Optional: show online/offline status and matching classes in the tooltip
                    tooltip = "✅ Online" if status else "❌ Offline"
                    possible_classes = [
                        component_class
                        for component_class in info.get("corresponding_class", [])
                        if component_class not in {"FlowchemComponent", "object"}
                    ]
                    details = (
                        "\n".join(
                            f"  - {component_class}"
                            for component_class in possible_classes
                        )
                        if possible_classes
                        else "  - No information available"
                    )
                    list_item.setToolTip(f"{text} - {tooltip}\n{details}")

                    used_by = self._component_using_url(urlc)
                    if used_by is not None:
                        self.add_to_lock(text, QIcon(figure), used_by)
                        self.OnlineList.takeItem(self.OnlineList.row(list_item))

    def associate_item(self, component: str, text: str | None = None):
        """Move selected items from OnlineList to LockList."""
        if text:
            for i in range(self.OnlineList.count()):
                item = self.OnlineList.item(i)
                if item.text() == text:
                    self.add_to_lock(item.text(), item.icon(), component)
                    self.OnlineList.takeItem(i)
                    return
        else:
            for item in self.OnlineList.selectedItems():
                self.add_to_lock(item.text(), item.icon(), component)
                self.OnlineList.takeItem(self.OnlineList.row(item))

    def add_to_lock(self, text, icon, component):
        """Add QListWidgetItem to B, with icon + button."""
        item = QListWidgetItem(icon, text)
        self.LockList.addItem(item)

        # Create small widget with label + button
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(4, 0, 4, 0)

        label = QLabel(text)
        label.setVisible(False)
        button = TransparentToolButton(FluentIcon.CANCEL_MEDIUM, self)
        button.setToolTip("Disconnect component")
        button.clicked.connect(
            lambda _, t=text, ic=icon: self.move_back_to_online(t, ic, component)
        )

        layout.addWidget(label)
        layout.addStretch()
        layout.addWidget(button)

        item.setSizeHint(widget.sizeHint())
        self.LockList.setItemWidget(item, widget)

    def move_back_to_online(self, text, icon, component):
        """Move the item back from LockList to OnlineList."""
        for i in range(self.LockList.count()):
            item = self.LockList.item(i)
            widget = self.LockList.itemWidget(item)
            if widget:
                label = widget.findChild(QLabel)
                if label and label.text() == text:
                    if self._parent:
                        self._parent.orchestrator.disassociate_component(component)
                    self.LockList.takeItem(i)
                    break
        self.OnlineList.addItem(QListWidgetItem(icon, text))

    def _component_using_url(self, urlc: str) -> str | None:
        if not self._parent:
            return None

        target_url = urlc.rstrip("/")
        for component in self._parent.orchestrator.components.values():
            if not component.inf.is_electronic:
                continue
            if str(component.url).rstrip("/") == target_url:
                return component.name
        return None


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication
    import sys

    app = QApplication(sys.argv)
    w = OnlineComponent(parent=None)
    w.update_list()
    w.show()
    sys.exit(app.exec_())
