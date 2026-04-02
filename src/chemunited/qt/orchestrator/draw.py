import re

from loguru import logger
from pydantic import BaseModel

from chemunited.qt.draw.elements.component import create_component, list_components
from chemunited.qt.shared.widgets.base_mode_editor import BaseModeDialog

from .core import OrchestratorCore


def call_component_model(figure: str) -> type[BaseModel]:
    categories, components = list_components()
    if figure not in components:
        raise AttributeError(f"Component {figure} not found")
    return components[figure].BASEMODE


class OrchestratorDraw(OrchestratorCore):
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
