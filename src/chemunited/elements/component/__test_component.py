from __future__ import annotations

import sys

from PyQt5.QtWidgets import QApplication

from chemunited.elements.component.component_factory import list_components
from chemunited.elements.component.graph_item import GraphComponent
from chemunited.shared.graph import GraphCore, SceneCore

FIGURE = "SyringePump"
SPACING_X = 200
SPACING_Y = 180


def _build_component(
    figure: str,
    cls: type[GraphComponent],
    position: tuple[int, int],
) -> GraphComponent:
    mode = cls.BASEMODE.model_validate(
        {
            "name": figure,
            "figure": figure,
            "position": position,
            "angle": 0,
        }
    )
    return cls(cls.METADATA.from_mode(mode))


def _add_all_components(scene: SceneCore) -> None:
    categories, components = list_components()
    for row, figures in enumerate(categories.values()):
        for col, figure in enumerate(figures):
            component = _build_component(
                figure,
                components[figure],
                (col * SPACING_X, row * SPACING_Y),
            )
            scene.addItem(component)


def _add_component(scene: SceneCore, figure: str) -> None:
    _, components = list_components()
    if figure not in components:
        raise KeyError(f"Component figure {figure!r} is not registered.")

    component = _build_component(figure, components[figure], (0, 0))
    scene.addItem(component)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    scene = SceneCore()

    if FIGURE == "all":
        _add_all_components(scene)
    else:
        _add_component(scene, FIGURE)

    view = GraphCore(scene)
    view.show()
    sys.exit(app.exec_())
