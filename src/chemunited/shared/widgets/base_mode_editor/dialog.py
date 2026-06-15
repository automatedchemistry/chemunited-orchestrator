from collections.abc import Mapping

from pydantic import BaseModel
from PyQt5.QtWidgets import QVBoxLayout
from qfluentwidgets import BodyLabel
from qframelesswindow import FramelessDialog

from .editor_widget import BaseModeEditorWidget


class BaseModeDialog(FramelessDialog):
    def __init__(
        self,
        model_class: type[BaseModel],
        instance: BaseModel | None = None,
        field_overrides: dict[str, Mapping[str, object]] | None = None,
        creation_mode: bool = False,
        title: str | None = None,
        content: str = "",
        parent=None,
    ):
        super().__init__(parent=parent)
        self.setWindowTitle(title or model_class.__name__)
        self.setResizeEnabled(False)

        self.editor_widget = BaseModeEditorWidget(
            model_class=model_class,
            instance=instance,
            field_overrides=field_overrides,
            creation_mode=creation_mode,
            parent=self,
        )
        self.editor_widget.saved.connect(self.on_save)  # type: ignore[attr-defined]
        self.editor_widget.cancelled.connect(self.reject)  # type: ignore[attr-defined]
        self._result_instance: BaseModel | None = None

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(16, self.titleBar.height() + 16, 16, 16)
        self.vBoxLayout.setSpacing(12)

        if content:
            self.contentLabel = BodyLabel(content, self)
            self.contentLabel.setWordWrap(True)
            self.vBoxLayout.addWidget(self.contentLabel)

        self.vBoxLayout.addWidget(self.editor_widget)

    def on_save(self, instance: BaseModel):
        self._result_instance = instance
        self.accept()

    def get_result_instance(self) -> BaseModel | None:
        return self._result_instance
