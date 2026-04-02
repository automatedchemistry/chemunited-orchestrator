"""Test that every registered component can be added to the scene without overlap.

Layout:
  - One row per category (sorted alphabetically)
  - One column per component within the category
  - 200 px horizontal spacing, 180 px vertical spacing (matches __test_component.py)

What is tested:
- Every component returned by list_components() can be added via orchestrator.add_component
- Each component is registered in orchestrator.components under its name
- Each component's graph item is present in the scene after adding
"""
import pytest
from pytestqt.qtbot import QtBot

from chemunited.qt.draw.elements.component import list_components
from chemunited.qt.setup import SetupWindow

SPACING_X = 200
SPACING_Y = 180


@pytest.fixture
def window(qtbot: QtBot):
    w = SetupWindow()
    qtbot.addWidget(w)
    w.show()
    qtbot.waitExposed(w)
    return w


def _grid_positions() -> list[tuple[str, float, float]]:
    """Return (component_name, x, y) for every component in grid order."""
    categories, _ = list_components()
    positions = []
    for row, (_, component_names) in enumerate(categories.items()):
        for col, name in enumerate(component_names):
            x = col * SPACING_X
            y = row * SPACING_Y
            positions.append((name, float(x), float(y)))
    return positions


class TestAllComponents:

    def test_all_components_added_to_orchestrator(self, window: SetupWindow, screenshot):
        screenshot(window, "initial")

        for name, x, y in _grid_positions():
            window.orchestrator.add_component(name=name, figure=name, position=(x, y))

        screenshot(window, "all_components_added")

        categories, _ = list_components()
        all_names = [name for names in categories.values() for name in names]
        for name in all_names:
            assert name in window.orchestrator.components, (
                f"Component '{name}' missing from orchestrator.components"
            )

    def test_all_components_graph_items_in_scene(self, window: SetupWindow, screenshot):
        for name, x, y in _grid_positions():
            window.orchestrator.add_component(name=name, figure=name, position=(x, y))

        screenshot(window, "scene_after_all_added")

        scene_items = set(window.scene_attribute.items())
        for name in window.orchestrator.components:
            component = window.orchestrator.components[name]
            assert component.graph in scene_items, (
                f"Graph item for '{name}' not found in scene"
            )

    def test_component_count_matches_registry(self, window: SetupWindow):
        categories, _ = list_components()
        expected_count = sum(len(names) for names in categories.values())

        for name, x, y in _grid_positions():
            window.orchestrator.add_component(name=name, figure=name, position=(x, y))

        assert len(window.orchestrator.components) == expected_count
