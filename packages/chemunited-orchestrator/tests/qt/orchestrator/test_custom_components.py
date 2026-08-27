"""Tests for project-local custom components in the orchestrator GUI.

Exercises the "build a custom component from your own project folder"
feature end to end at the orchestrator level: register a component and a
custom GraphComponent subclass the same way a project's
customizations/components/__init__.py + customizations/components/graph.py
would (see chemunited_core.figure_registry.register_component and
chemunited.elements.component.project_glossary.load_project_graph_components),
then confirm it shows up under a "Custom" palette group and renders using the
custom subclass when added to the scene.

Registration must happen at import time, in this order — component first,
then the GraphComponent subclass — exactly like a real project's
customizations/components/__init__.py is loaded before
customizations/components/graph.py, since GraphComponent.__init_subclass__
requires FIGURE to already be in COMPONENTS.
"""

import pytest
from pytestqt.qtbot import QtBot

from chemunited.elements.component.component_factory import (
    list_components,
    set_project_graph_components,
)
from chemunited.elements.component.graph_item import GraphComponent
from chemunited.setup import SetupWindow
from chemunited_core.components import ComponentData, ComponentMode
from chemunited_core.figure_registry import (
    ComponentDefinition,
    clear_project_components,
    register_component,
)

FIGURE_NAME = "TestCustomComponent"


class _CustomMode(ComponentMode):
    pass


class _CustomData(ComponentData):
    pass


register_component(FIGURE_NAME, ComponentDefinition(_CustomData, _CustomMode))


class _CustomGraph(GraphComponent[_CustomData]):
    FIGURE = FIGURE_NAME


@pytest.fixture(scope="module", autouse=True)
def _custom_component_lifecycle():
    set_project_graph_components({FIGURE_NAME: _CustomGraph})
    yield
    set_project_graph_components({})
    clear_project_components()


@pytest.fixture
def window(qtbot: QtBot):
    w = SetupWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


def test_custom_component_is_grouped_under_custom_category() -> None:
    categories, components = list_components()

    assert FIGURE_NAME in categories["Custom"]
    assert components[FIGURE_NAME] is _CustomGraph


def test_custom_component_can_be_added_to_scene(window: SetupWindow) -> None:
    window.orchestrator.add_component(
        name=FIGURE_NAME, figure=FIGURE_NAME, position=(0.0, 0.0)
    )

    assert FIGURE_NAME in window.orchestrator.components
    component = window.orchestrator.components[FIGURE_NAME]
    assert isinstance(component.graph, _CustomGraph)
    assert component.graph in set(window.scene_attribute.items())
