from typing import TYPE_CHECKING, Union, override

from pydantic import BaseModel
from PyQt5.QtCore import pyqtSlot
from qfluentwidgets import FluentIcon, NavigationItemPosition

from chemunited.qt.shared.widgets.main_window import WindowBase

from .properties import PropertiesWidget

if TYPE_CHECKING:
    from chemunited.qt.draw.elements.component import ElectronicManager, UtensilManager


class ComponentWidget(WindowBase):
    def __init__(
        self, component: Union[UtensilManager, ElectronicManager], parent=None
    ):
        super().__init__(parent)
        self.component = component
        self.TITLE = f"{component.name} Properties"
        self.buildUi()
        self._connect_signals()

    @override
    def initLayout(self):
        super().initLayout()
        self.properties_widget = PropertiesWidget(
            component=self.component,
            parent=self,
        )

    @override
    def initNavigation(self):
        super().initNavigation()
        self.addSubInterface(
            interface=self.properties_widget,
            icon=FluentIcon.EDIT,
            text="Properties",
            position=NavigationItemPosition.TOP,
        )

    @pyqtSlot(BaseModel)
    def save(self, model: BaseModel):
        self.component.graph.sync(model)

    def _connect_signals(self):
        self.properties_widget.saved.connect(self.save)
