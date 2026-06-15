from __future__ import annotations

from typing import TYPE_CHECKING, Union

from PyQt5.QtWidgets import QWidget

from chemunited.shared.widgets.base_mode_editor import BaseModeEditorWidget

if TYPE_CHECKING:
    from chemunited.elements.component import ElectronicManager, UtensilManager


class PropertiesWidget(BaseModeEditorWidget):
    def __init__(
        self,
        component: Union[UtensilManager, ElectronicManager],
        parent: QWidget | None = None,
    ):
        self._component = component
        super().__init__(
            model_class=component.graph.BASEMODE,
            instance=component.graph.base_mode_instance,
            parent=parent,
        )

    def showEvent(self, event) -> None:
        """Reload card values from the current component state each time the panel is shown."""
        instance = self._component.graph.base_mode_instance
        self._instance = instance
        for name, card in self._cards.items():
            value = getattr(instance, name, None)
            if value is not None:
                card.set_value(value)
        super().showEvent(event)
