from __future__ import annotations

from typing import TYPE_CHECKING, Union, override

from pydantic import BaseModel
from PyQt5.QtCore import pyqtSlot
from qfluentwidgets import FluentIcon, NavigationItemPosition

from chemunited.qt.shared.widgets.main_window import WindowBase
from chemunited.qt.shared.icon import OrchestratorIcon
from .properties import PropertiesWidget
from .connectivity import ConnectivityWidget

if TYPE_CHECKING:
    from chemunited.qt.elements.component import ElectronicManager, UtensilManager


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
        if self.component.inf.is_electronic:
            self.connectivity_widget = ConnectivityWidget(
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
        if self.component.inf.is_electronic:
            self.addSubInterface(
                interface=self.connectivity_widget,
                icon=OrchestratorIcon.WIFI,
                text="Connectivity",
                position=NavigationItemPosition.TOP,
            )

    @pyqtSlot(BaseModel)
    def save(self, model: BaseModel):
        self.component.graph.sync(model)

    def _connect_signals(self):
        self.properties_widget.saved.connect(self.save)
