from PyQt5.QtWidgets import QWidget, QVBoxLayout
from typing import TYPE_CHECKING, Union   

from chemunited.qt.shared.widgets.base_mode_editor import BaseModeEditorWidget

if TYPE_CHECKING:
    from chemunited.qt.draw.elements.component import UtensilManager, ElectronicManager


class PropertiesWidget(BaseModeEditorWidget):
    def __init__(self, component: Union[UtensilManager, ElectronicManager], parent: QWidget | None = None):
        super().__init__(
            model_class=component.graph.BASEMODE,
            instance=component.graph.base_mode_instance,
            parent=parent,
        )
