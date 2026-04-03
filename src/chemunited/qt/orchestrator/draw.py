import re

from loguru import logger
from pydantic import BaseModel
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import QGraphicsItem

from chemunited.core.common.enums import ConnectionType
from chemunited.core.connections import EdgeData, EdgeMode
from chemunited.core.utils.internal_quantity import ChemUnitQuantity
from chemunited.qt.draw.elements.component import create_component, list_components
from chemunited.qt.draw.elements.component.component_parts.connection_point import (
    ConnectionPoint,
)
from chemunited.qt.draw.elements.connection import (
    BaseConnectionItem,
    ElectricalConnectionItem,
    HeatConnectionItem,
    HydraulicConnectionItem,
    MovementConnectionItem,
)
from chemunited.qt.shared.widgets.base_mode_editor import BaseModeDialog

from .core import OrchestratorCore

_CONNECTION_FACTORY: dict[ConnectionType, type[BaseConnectionItem]] = {
    ConnectionType.HYDRAULIC: HydraulicConnectionItem,
    ConnectionType.ELECTRONIC: ElectricalConnectionItem,
    ConnectionType.HEAT: HeatConnectionItem,
    ConnectionType.MOVEMENT: MovementConnectionItem,
}


def call_component_model(figure: str) -> type[BaseModel]:
    categories, components = list_components()
    if figure not in components:
        raise AttributeError(f"Component {figure} not found")
    return components[figure].BASEMODE


class OrchestratorDraw(OrchestratorCore):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_ref.drawGraph.connection_requested.connect(
            self.request_add_connection
        )

    def _suggest_name(self, figure: str) -> str:
        base = re.sub(r"[^A-Za-z0-9]", "", figure) or "Component"
        existing = set(self.components.keys())

        if base not in existing:
            return base

        index = 2
        while f"{base}{index}" in existing:
            index += 1

        return f"{base}{index}"

    def request_add_component(
        self,
        figure: str,
        position: tuple[float, float],
    ):
        mode_class = call_component_model(figure)
        suggested_name = self._suggest_name(figure)

        dialog = BaseModeDialog(
            model_class=mode_class,
            instance=mode_class(name=suggested_name, figure=figure, position=position),
            field_overrides={"name": {"editable": True}},
            parent=self.parent_ref,
        )

        if not dialog.exec():
            return None

        mode = dialog.get_result_instance()
        if mode is None:
            return

        payload = mode.model_dump()
        self.add_component(**payload)

    def add_component(
        self,
        *,
        name: str,
        figure: str,
        position: tuple[float, float],
        **kwargs,
    ):
        if not name:
            raise ValueError("Component name is required")
        if name in self.components:
            raise ValueError(f"Component '{name}' already exists")

        component = create_component(
            figure=figure,
            name=name,
            position=position,
            **kwargs,
        )
        self.components[name] = component
        self.parent_ref.scene_attribute.addItem(component.graph)
        logger.bind(window=self.parent_ref.WINDOW_TYPE).info(
            f"Component {component.inf.COMPONENT_TYPE.name} name '{name}' was successfully created."
        )

    @pyqtSlot(ConnectionPoint, ConnectionPoint)
    def request_add_connection(self, origin: ConnectionPoint, destiny: ConnectionPoint):
        if origin.parent_ref._data.name == destiny.parent_ref._data.name:
            raise ValueError("Cannot connect a component to itself")

        self.add_connection(
            origin=origin.parent_ref._data.name,
            destiny=destiny.parent_ref._data.name,
            origin_port=int(origin.id_connection),
            destiny_port=int(destiny.id_connection),
        )

    def add_connection(
        self,
        origin: str,
        destiny: str,
        origin_port: int = 2,
        destiny_port: int = 1,
        **kwargs,
    ):
        # Verify if the components do exist
        if origin not in self.components:
            raise ValueError(f"Component '{origin}' does not exist")
        if destiny not in self.components:
            raise ValueError(f"Component '{destiny}' does not exist")

        # Verify if the ports do exist
        if origin_port not in self.components[origin].inf.ports_by_number:
            raise ValueError(
                f"Port '{origin_port}' does not exist in component '{origin}'"
            )
        if destiny_port not in self.components[destiny].inf.ports_by_number:
            raise ValueError(
                f"Port '{destiny_port}' does not exist in component '{destiny}'"
            )

        # Verify if the origin and detination has the same category
        port_1_object = self.components[origin].inf.ports_by_number[origin_port]
        port_2_object = self.components[destiny].inf.ports_by_number[destiny_port]
        if port_1_object.category != port_2_object.category:
            raise ValueError(
                "Origin and detination must have the same category. Now they are: "
                f"{port_1_object.category.name} and {port_2_object.category.name}"
            )

        # Resolve the ConnectionPoint UI objects (needed for scenePos)
        origin_cp = self.components[origin].graph.get_connection_point(origin_port)
        destiny_cp = self.components[destiny].graph.get_connection_point(destiny_port)

        if port_1_object.category == ConnectionType.HYDRAULIC:
            diameter = kwargs.get("diameter", ChemUnitQuantity("1 mm"))
            if diameter.to_base_units().magnitude <= 0:
                raise ValueError("Diameter must be greater than 0")
            length = kwargs.get("length", ChemUnitQuantity("100 mm"))
            if length.to_base_units().magnitude <= 0:
                raise ValueError("Length must be greater than 0")
        else:
            length = ChemUnitQuantity("0 mm")
            diameter = ChemUnitQuantity("0 mm")

        mode = EdgeMode(
            origin=origin,
            destination=destiny,
            origin_port=origin_port,
            destination_port=destiny_port,
            classification=port_1_object.category,
            length=length,
            diameter=diameter,
            straight_path=kwargs.get("straight_path", True),
            air_pressure_line=kwargs.get("air_pressure_line", False),
            inflection_points=kwargs.get("inflection_points", []),
        )
        data = EdgeData.from_mode(mode)

        if data.name in self.connections:
            raise ValueError(f"Connection '{data.name}' already exists")

        cls = _CONNECTION_FACTORY.get(port_1_object.category)
        if cls is None:
            raise ValueError(f"Unknown connection category: {port_1_object.category}")
        connection = cls(origin_port=origin_cp, destination_port=destiny_cp, data=data)

        self.parent_ref.scene_attribute.addItem(connection)
        self.connections[data.name] = connection

    def _is_item_or_descendant(
        self, item: QGraphicsItem, candidate: QGraphicsItem | None
    ) -> bool:
        current = candidate
        while current is not None:
            if current is item:
                return True
            current = current.parentItem()
        return False

    def _prepare_item_for_removal(self, item: QGraphicsItem) -> None:
        scene = self.parent_ref.scene_attribute

        mouse_grabber = scene.mouseGrabberItem()
        if mouse_grabber is not None and self._is_item_or_descendant(
            item, mouse_grabber
        ):
            mouse_grabber.ungrabMouse()

        focus_item = scene.focusItem()
        if focus_item is not None and self._is_item_or_descendant(item, focus_item):
            scene.setFocusItem(None)

        if item.isSelected():
            item.setSelected(False)

        item.setEnabled(False)
        item.setVisible(False)

    def remove_connection(self, name: str) -> None:
        if name not in self.connections:
            raise ValueError(f"Connection '{name}' does not exist")
        connection = self.connections.pop(name)
        connection.remove()
        self._prepare_item_for_removal(connection)
        self.parent_ref.scene_attribute.removeItem(connection)
        self.parent_ref.scene_attribute.update()
        logger.bind(window=self.parent_ref.WINDOW_TYPE).info(
            f"Connection '{name}' was successfully removed."
        )

    def remove_component(self, name: str) -> None:
        if name not in self.components:
            raise ValueError(f"Component '{name}' does not exist")
        # Remove any connections that reference this component before removing it,
        # otherwise their port callbacks will dangle on a deleted graph item.
        attached = [
            conn_name
            for conn_name, conn in self.connections.items()
            if conn.inf.origin == name or conn.inf.destination == name
        ]
        for conn_name in attached:
            self.remove_connection(conn_name)
        component = self.components.pop(name)
        self._prepare_item_for_removal(component.graph)
        self.parent_ref.scene_attribute.removeItem(component.graph)
        self.parent_ref.scene_attribute.update()
        logger.bind(window=self.parent_ref.WINDOW_TYPE).info(
            f"Component '{name}' was successfully removed."
        )
