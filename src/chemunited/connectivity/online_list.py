from typing import TYPE_CHECKING, Optional
from urllib.parse import urlsplit, urlunsplit

from loguru import logger
from PyQt5.QtCore import QMimeData, Qt
from PyQt5.QtGui import QColor, QDrag, QFont, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QListWidgetItem, QVBoxLayout, QWidget
from qfluentwidgets import (
    EditableComboBox,
    FluentIcon,
    ListWidget,
    PushButton,
    StrongBodyLabel,
    TransparentToolButton,
    isDarkTheme,
)

from chemunited.shared.icon import OrchestratorIcon
from chemunited.utils.flowchem_listener import (
    FLOWCHEM_SERVERS,
    access_url,
)

if TYPE_CHECKING:
    from chemunited.setup import SetupWindow


class OnlineList(ListWidget):
    MIME = "application/x-chemunited-online-list"

    def __init__(self, api_obj, parent=None):
        super().__init__(parent)
        self.api_obj = api_obj
        self.setDragEnabled(True)
        # Important: allow dragging outside the widget
        self.setDefaultDropAction(Qt.MoveAction)  # type: ignore[attr-defined]

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
            pixmap.fill(Qt.transparent)  # type: ignore[attr-defined]

            painter = QPainter(pixmap)

            # Rounded background (light or dark depending on theme)
            bg_color = (
                QColor(40, 40, 40, 180) if isDarkTheme() else QColor(240, 240, 240, 200)
            )
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(bg_color)
            painter.setPen(Qt.NoPen)  # type: ignore[attr-defined]
            painter.drawRoundedRect(0, 0, width, height, 8, 8)

            # Draw icon
            if not icon.isNull():
                icon_pix = icon.pixmap(24, 24)
                painter.drawPixmap(6, (height - 24) // 2, icon_pix)

            # Draw text
            painter.setFont(QFont("Segoe UI", 9))
            painter.setPen(
                Qt.white if isDarkTheme() else Qt.black  # type: ignore[attr-defined]
            )
            painter.drawText(36, 22, text)

            painter.end()

            # Set this custom pixmap as the drag image
            drag.setPixmap(pixmap)
            drag.setHotSpot(pixmap.rect().center())

            drag.exec_(Qt.CopyAction)  # type: ignore[attr-defined]


class OnlineComponent(QWidget):
    def __init__(self, parent):
        super().__init__()
        self._parent: Optional["SetupWindow"] = parent
        layout = QVBoxLayout(self)

        self.api = EditableComboBox(self)
        self.api.setPlaceholderText("-")
        self.api.currentTextChanged.connect(self.select_api)
        self.api.textEdited.connect(self._on_manual_api_edited)
        self.api.returnPressed.connect(self.submit_manual_api)
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

        self.update_button = PushButton(OrchestratorIcon.UPDATE, "Update List", self)
        self.update_button.clicked.connect(self.update_list)
        layout.addWidget(self.update_button)

    def update_list(self):
        self.update_button.setEnabled(True)
        self.api.clear()
        self.api.setText("")
        FLOWCHEM_SERVERS.update()
        for item in FLOWCHEM_SERVERS.servers:
            self.api.addItem(item)

    def _on_manual_api_edited(self, _text: str):
        self.update_button.setEnabled(False)

    def submit_manual_api(self):
        raw_url = self.api.text()
        normalized_url = self._normalize_api_url(raw_url)
        if not normalized_url:
            self._reject_manual_api(
                raw_url,
                normalized_url,
                "Flowchem API address is empty or invalid.",
            )
            return

        self._show_busy_status(
            "Inspecting FlowChem API",
            f"Reading {normalized_url}/openapi.json...",
        )
        ok, data = access_url(f"{normalized_url}/openapi.json", timeout=1)
        if not ok:
            self._reject_manual_api(
                raw_url,
                normalized_url,
                "Flowchem API is not reachable at {}.",
                normalized_url,
            )
            return

        if not isinstance(data, dict) or not isinstance(data.get("paths"), dict):
            self._reject_manual_api(
                raw_url,
                normalized_url,
                "Flowchem API at {} does not expose a valid openapi paths object.",
                normalized_url,
            )
            return

        if "/startup_config" not in data["paths"]:
            self._reject_manual_api(
                raw_url,
                normalized_url,
                "Flowchem API at {} does not expose startup_config. "
                "Update Flowchem for smooth connection with chemunited.",
                normalized_url,
            )
            return

        FLOWCHEM_SERVERS.register_openapi(normalized_url, data)
        self._select_registered_api(raw_url=raw_url, normalized_url=normalized_url)
        self.update_button.setEnabled(True)
        component_count = sum(
            len(components)
            for components in FLOWCHEM_SERVERS.servers[normalized_url].values()
        )
        self._finish_busy_status(f"Registered {component_count} FlowChem component(s).")

    @staticmethod
    def _normalize_api_url(raw_url: str) -> str:
        url = raw_url.strip().rstrip("/")
        if not url:
            return ""

        if "://" not in url:
            url = f"http://{url}"

        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return ""

        path = parsed.path.rstrip("/")
        return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))

    def _select_registered_api(self, raw_url: str, normalized_url: str):
        signals_blocked = self.api.blockSignals(True)
        try:
            if raw_url != normalized_url:
                raw_index = self.api.findText(raw_url)
                if raw_index >= 0:
                    self.api.removeItem(raw_index)

            index = self.api.findText(normalized_url)
            if index < 0:
                self.api.addItem(normalized_url)
                index = self.api.findText(normalized_url)

            self.api.setCurrentIndex(index)
            self.api.setText(normalized_url)
        finally:
            self.api.blockSignals(signals_blocked)

        self.select_api(normalized_url)

    def _reject_manual_api(
        self, raw_url: str, normalized_url: str, message: str, *args
    ):
        self.OnlineList.clear()
        self._remove_unregistered_api_items(raw_url, normalized_url)
        self.api.setText(raw_url)
        self.update_button.setEnabled(True)
        formatted = message.format(*args) if args else message
        self._fail_busy_status(formatted)
        logger.warning(message, *args)

    def _show_busy_status(self, title: str, message: str) -> None:
        if self._parent is None:
            return
        show_busy_status = getattr(self._parent, "show_busy_status", None)
        if callable(show_busy_status):
            show_busy_status(title, message)

    def _finish_busy_status(self, message: str) -> None:
        if self._parent is None:
            return
        finish_busy_status = getattr(self._parent, "finish_busy_status", None)
        if callable(finish_busy_status):
            finish_busy_status(message)

    def _fail_busy_status(self, message: str) -> None:
        if self._parent is None:
            return
        fail_busy_status = getattr(self._parent, "fail_busy_status", None)
        if callable(fail_busy_status):
            fail_busy_status(message)

    def _remove_unregistered_api_items(self, *urls: str):
        for url in dict.fromkeys(urls):
            if not url or url in FLOWCHEM_SERVERS.servers:
                continue

            index = self.api.findText(url)
            if index >= 0:
                self.api.removeItem(index)

    def select_api(self, item):
        url = item.rstrip("/")
        self.OnlineList.clear()

        if url in FLOWCHEM_SERVERS.servers:
            for device in FLOWCHEM_SERVERS.servers[url]:
                for component in FLOWCHEM_SERVERS.servers[url][device]:
                    urlc = f"{url}/{device}/{component}"
                    figure = OrchestratorIcon.COMPONENT_ICON.path()

                    # Create the list item with icon + text
                    text = f"{device}/{component}"
                    list_item = QListWidgetItem(QIcon(figure), text)
                    self.OnlineList.addItem(list_item)

                    list_item.setToolTip(f"{text}\nDiscovered from openapi.json")

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
    import sys

    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    w = OnlineComponent(parent=None)
    w.update_list()
    w.show()
    sys.exit(app.exec_())
