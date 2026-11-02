from PyQt5.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import CaptionLabel, LineEdit, isDarkTheme


class NodeMetadataEditor(QWidget):
    """Compact editor for the author-facing workflow node metadata."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.label_edit = LineEdit(self)
        self.label_edit.setPlaceholderText("Block label")
        self.description_edit = LineEdit(self)
        self.description_edit.setPlaceholderText("Block description")

        # Ensure text color is visible in dark mode
        if isDarkTheme():
            text_color = "rgba(255, 255, 255, 0.85)"
            label_style = f"color: {text_color};"
            desc_style = f"color: {text_color};"
            # LineEdit doesn't support placeholder color directly via stylesheet
            # in all Qt versions, so we set the main text color
            self.label_edit.setStyleSheet(label_style)
            self.description_edit.setStyleSheet(desc_style)

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
        caption = CaptionLabel(title, field)
        if isDarkTheme():
            caption.setStyleSheet("color: rgba(255, 255, 255, 0.85);")
        layout.addWidget(caption)
        layout.addWidget(editor)
        return field

    def set_values(self, label: str, description: str) -> None:
        self.label_edit.setText(label)
        self.description_edit.setText(description)

    def values(self) -> tuple[str, str]:
        return self.label_edit.text().strip(), self.description_edit.text().strip()
