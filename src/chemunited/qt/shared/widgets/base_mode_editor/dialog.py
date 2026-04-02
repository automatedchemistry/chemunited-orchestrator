from collections.abc import Mapping

from pydantic import BaseModel
from qfluentwidgets import Dialog

from .editor_widget import BaseModeEditorWidget


class BaseModeDialog(Dialog):
    def __init__(
        self,
        model_class: type[BaseModel],
        instance: BaseModel | None = None,
        field_overrides: dict[str, Mapping[str, object]] | None = None,
        title: str | None = None,
        content: str = "",
        parent=None,
    ):
        super().__init__(title or model_class.__name__, content, parent)
        self.editor_widget = BaseModeEditorWidget(
            model_class=model_class,
            instance=instance,
            field_overrides=field_overrides,
        )
        self.contentLabel.hide()
        self.hideYesButton()
        self.hideCancelButton()
        self.textLayout.addWidget(self.editor_widget)
        self.editor_widget.saved.connect(self.on_save)
        self.editor_widget.cancelled.connect(self.reject)
        self._result_instance: BaseModel | None = None

    def on_save(self, instance: BaseModel):
        self._result_instance = instance
        self.accept()

    def get_result_instance(self) -> BaseModel | None:
        return self._result_instance
