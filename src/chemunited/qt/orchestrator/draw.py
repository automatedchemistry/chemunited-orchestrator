from loguru import logger

from chemunited.qt.draw.elements.component import create_component

from .core import OrchestratorCore


class OrchestratorDraw(OrchestratorCore):
    def add_component(
        self,
        name: str = "",
        figure: str = "",
        position: tuple[float, float] = (0, 0),
        **kwargs,
    ) -> None:
        if name in self.components:
            raise AttributeError(
                f"There is another component using the name '{name}'. Use another name to identify it!"
            )
        component = create_component(
            figure=figure, name=name, position=position, **kwargs
        )
        self.components[name] = component

        self.parent_ref.scene.addItem(component.graph)

        logger.bind(window=self.parent_ref.WINDOW_TYPE).info(
            f"Component {component.inf.COMPONENT_TYPE.name} name: '{name}' was successfully created."
        )
