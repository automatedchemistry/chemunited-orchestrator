from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, LineEdit


class NodeMetadataEditor(QWidget):
    """Compact editor for the author-facing workflow node metadata."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.label_edit = LineEdit(self)
        self.label_edit.setPlaceholderText("Block label")
        self.description_edit = LineEdit(self)
        self.description_edit.setPlaceholderText("Block description")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._field("Label", self.label_edit), stretch=1)
        layout.addWidget(self._field("Description", self.description_edit), stretch=2)

    def _field(self, title: str, editor: LineEdit) -> QWidget:
        field = QWidget(self)
        layout = QVBoxLayout(field)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(CaptionLabel(title, field))
        layout.addWidget(editor)
        return field

    def set_values(self, label: str, description: str) -> None:
        self.label_edit.setText(label)
        self.description_edit.setText(description)

    def values(self) -> tuple[str, str]:
        return self.label_edit.text().strip(), self.description_edit.text().strip()
