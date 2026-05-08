from typing import TYPE_CHECKING

from loguru import logger
from PyQt5.QtWidgets import QWidget

from chemunited.qt.elements.component.connectivity import ComponentConnnectivity
from chemunited.qt.shared.widgets.base_mode_editor import BaseModeEditorWidget

if TYPE_CHECKING:
    from chemunited.qt.elements.component import ElectronicManager


class ConnectivityWidget(BaseModeEditorWidget):
    def __init__(self, component: ElectronicManager, parent: QWidget | None = None):
        self._component = component
        super().__init__(
            model_class=ComponentConnnectivity,
            instance=component.connectivity,
            parent=parent,
        )

    def save(self) -> None:
        """Save the connectivity."""
        super().save()
        if self._component.is_online:
            logger.success(
                f"Component {self._component.name} was connected to "
                f"{self._component.connectivity.url} successfully"
            )
            self._component.graph.set_online(
                True, self._component.connectivity.url_component
            )
        else:
            logger.error(f"Component {self._component.name} was not connected.")
            self._component.graph.set_online(False, "")
