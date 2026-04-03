from chemunited.qt.shared.widgets.main_window import WindowBase
from .properties import PropertiesWidget
from typing import TYPE_CHECKING, Union
from qfluentwidgets import FluentIcon, NavigationItemPosition

if TYPE_CHECKING:
    from chemunited.qt.draw.elements.component import UtensilManager, ElectronicManager

class ComponentWidget(WindowBase):
    def __init__(self, component: Union[UtensilManager, ElectronicManager], parent=None):
        super().__init__(parent)
        self.component = component

    def initLayout(self):
        super().initLayout()
        self.properties_widget = PropertiesWidget(
            component=self.component,
            parent=self,
        )

    def initNavigation(self):
        super().initNavigation()
        self.addSubInterface(
            widget=self.properties_widget,
            icon=FluentIcon.EDIT,
            text="Properties",
            position=NavigationItemPosition.TOP,
        )