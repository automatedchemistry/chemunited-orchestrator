import re

from chemunited_core.common.enums import ConnectionType
from chemunited_core.components.internals import DEFAULT_INVENTORY_KEY
from chemunited_core.connections import EdgeData, EdgeMode
from chemunited_quantities import ChemUnitQuantity
from loguru import logger
from pydantic import BaseModel
from PyQt5.QtCore import pyqtSlot
from PyQt5.QtWidgets import QGraphicsItem

from chemunited.elements.component import create_component, list_components
from chemunited.elements.component.component_parts.connection_point import (
    ConnectionPoint,
)
from chemunited.elements.connection import (
    BaseConnectionItem,
    ElectricalConnectionItem,
    HeatConnectionItem,
    HydraulicConnectionItem,
    MovementConnectionItem,
)
from chemunited.shared.widgets.base_mode_editor import BaseModeDialog

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


def _log_draw_error(parent_ref, message: str, exc: Exception | None = None) -> None:
    bound_logger = logger.bind(window=parent_ref.WINDOW_TYPE)
    if exc is not None:
        bound_logger = bound_logger.opt(exception=exc)
    bound_logger.error(message)


class OrchestratorDraw(OrchestratorCore):
    def __init__(self, parent=None):
        super().__init__(parent)
        if hasattr(self.parent_ref, "drawGraph"):
            self.parent_ref.drawGraph.connection_requested.connect(  # type: ignore
                self.request_add_connection
            )

    def _apply_draw_layer_order(self) -> None:
        draw_graph = getattr(self.parent_ref, "drawGraph", None)
        apply_layer_order = getattr(draw_graph, "apply_layer_order", None)
        if callable(apply_layer_order):
            apply_layer_order()

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
        try:
            mode_class = call_component_model(figure)
        except AttributeError as exc:
            _log_draw_error(self.parent_ref, str(exc), exc)
            return
        suggested_name = self._suggest_name(figure)

        dialog = BaseModeDialog(
            model_class=mode_class,
            instance=mode_class(name=suggested_name, figure=figure, position=position),
            creation_mode=True,
            parent=self.parent_ref,
        )

        if not dialog.exec():
            return None

        mode = dialog.get_result_instance()
        if mode is None:
            return

        payload = dict(mode)
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
            _log_draw_error(self.parent_ref, "Component name is required.")
            return
        if name in self.components:
            _log_draw_error(self.parent_ref, f"Component '{name}' already exists.")
            return

        component = create_component(
            figure=figure,
            name=name,
            position=position,
            **kwargs,
        )
        self.components[name] = component
        self.parent_ref.scene_attribute.addItem(component.graph)
        self._apply_draw_layer_order()
        logger.bind(window=self.parent_ref.WINDOW_TYPE).info(
            f"Component {component.inf.COMPONENT_TYPE.name} name '{name}' was successfully created."
        )

    @pyqtSlot(ConnectionPoint, ConnectionPoint)
    def request_add_connection(self, origin: ConnectionPoint, destiny: ConnectionPoint):
        if origin.parent_ref._data.name == destiny.parent_ref._data.name:
            _log_draw_error(self.parent_ref, "Cannot connect a component to itself.")
            return

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
            _log_draw_error(self.parent_ref, f"Component '{origin}' does not exist.")
            return
        if destiny not in self.components:
            _log_draw_error(self.parent_ref, f"Component '{destiny}' does not exist.")
            return

        # Verify if the ports do exist
        if origin_port not in self.components[origin].inf.ports_by_number:
            _log_draw_error(
                self.parent_ref,
                f"Port '{origin_port}' does not exist in component '{origin}'.",
            )
            return
        if destiny_port not in self.components[destiny].inf.ports_by_number:
            _log_draw_error(
                self.parent_ref,
                f"Port '{destiny_port}' does not exist in component '{destiny}'.",
            )
            return

        # Verify if the origin and destination have the same category
        port_1_object = self.components[origin].inf.ports_by_number[origin_port]
        port_2_object = self.components[destiny].inf.ports_by_number[destiny_port]
        requested_classification = kwargs.get("classification")
        classification = (
            port_1_object.category
            if requested_classification is None
            else ConnectionType(requested_classification)
        )
        if (
            requested_classification is None
            and port_1_object.category != port_2_object.category
        ):
            _log_draw_error(
                self.parent_ref,
                "Origin and destination must have the same category. "
                f"Got: {port_1_object.category.name} and {port_2_object.category.name}.",
            )
            return

        # Resolve the ConnectionPoint UI objects (needed for scenePos)
        origin_cp = self.components[origin].graph.get_connection_point(origin_port)
        destiny_cp = self.components[destiny].graph.get_connection_point(destiny_port)

        if classification == ConnectionType.HYDRAULIC:
            diameter = ChemUnitQuantity.from_any(
                kwargs.get("diameter", ChemUnitQuantity("1 mm")), default_unit="mm"
            )
            if diameter.to_base_units().magnitude <= 0:
                _log_draw_error(self.parent_ref, "Diameter must be greater than 0.")
                return
            length = ChemUnitQuantity.from_any(
                kwargs.get("length", ChemUnitQuantity("100 mm")), default_unit="mm"
            )
            if length.to_base_units().magnitude <= 0:
                _log_draw_error(self.parent_ref, "Length must be greater than 0.")
                return
        else:
            length = ChemUnitQuantity("0 mm")
            diameter = ChemUnitQuantity("0 mm")

        mode = EdgeMode(
            origin=origin,
            destination=destiny,
            origin_port=origin_port,
            destination_port=destiny_port,
            classification=classification,
            length=length,
            diameter=diameter,
            straight_path=kwargs.get("straight_path", True),
            air_pressure_line=kwargs.get("air_pressure_line", False),
            inflection_points=kwargs.get("inflection_points", []),
        )
        data = EdgeData.from_mode(mode)

        if data.name in self.connections:
            _log_draw_error(
                self.parent_ref, f"Connection '{data.name}' already exists."
            )
            return

        cls = _CONNECTION_FACTORY.get(classification)
        if cls is None:
            _log_draw_error(
                self.parent_ref, f"Unknown connection category: {classification}."
            )
            return
        connection = cls(origin_port=origin_cp, destination_port=destiny_cp, data=data)

        self.parent_ref.scene_attribute.addItem(connection)
        self.connections[data.name] = connection
        self._apply_draw_layer_order()

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
            _log_draw_error(self.parent_ref, f"Connection '{name}' does not exist.")
            return
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
            _log_draw_error(self.parent_ref, f"Component '{name}' does not exist.")
            return
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
        if component._widget is not None:
            component._widget.close()
        self._prepare_item_for_removal(component.graph)
        self.parent_ref.scene_attribute.removeItem(component.graph)
        self.parent_ref.scene_attribute.update()
        logger.bind(window=self.parent_ref.WINDOW_TYPE).info(
            f"Component '{name}' was successfully removed."
        )

    def show_properties(self, name: str) -> None:
        if name not in self.components:
            _log_draw_error(self.parent_ref, f"Component '{name}' does not exist.")
            return
        component = self.components[name]
        component.widget.show()

    def show_connection_properties(self, name: str) -> None:
        if name not in self.connections:
            _log_draw_error(self.parent_ref, f"Connection '{name}' does not exist.")
            return
        connection = self.connections[name]

        dialog = BaseModeDialog(
            model_class=EdgeMode,
            instance=connection.base_mode_instance,
            field_overrides={
                "straight_path": {"visible": False},
                "air_pressure_line": {"visible": False},
            },
            title=f"Connection Properties — {connection.inf.origin} → {connection.inf.destination}",
            parent=self.parent_ref,
        )
        if not dialog.exec():
            return

        mode = dialog.get_result_instance()
        if mode is None:
            return
        if not isinstance(mode, EdgeMode):
            mode = EdgeMode.model_validate(mode)
        connection.sync(mode)
        logger.bind(window=self.parent_ref.WINDOW_TYPE).info(
            f"Connection '{name}' properties updated."
        )

    def fill_iventory(
        self,
        component: str,
        iventory: str = DEFAULT_INVENTORY_KEY,
        phase: str = "liq",
        content: dict = {},
    ):
        if component not in self.components:
            return
        comp = self.components[component]
        inventories = getattr(comp.inf, "internal_inventories", {})
        node = inventories.get(iventory)
        if node is None:
            return
        phase_content = node.liq_content if phase == "liq" else node.gas_content
        if "volume" in content:
            phase_content.volume = float(content["volume"])
        if "initial_species" in content:
            phase_content.initial_species = {
                str(k): float(v)
                for k, v in content["initial_species"].items()
                if float(v) > 0.0
            }
        comp.graph.sync_visuals()
