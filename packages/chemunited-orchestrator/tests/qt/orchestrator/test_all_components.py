"""Test that every registered component can be added and removed from the scene.

Layout:
  - One row per category (sorted alphabetically)
  - One column per component within the category
  - 200 px horizontal spacing, 180 px vertical spacing

What is tested:
- Every component returned by list_components() can be added via orchestrator.add_component
- Each component is registered in orchestrator.components under its name
- Each component's graph item is present in the scene after adding
- Every component can be removed via orchestrator.remove_component
- After removing all components, orchestrator.components is empty
- After removing all components, no graph items remain in the scene
"""

import pytest
from pytestqt.qtbot import QtBot

from chemunited.elements.component.component_factory import list_components
from chemunited.setup import SetupWindow

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


def _add_all(window: SetupWindow) -> None:
    for name, x, y in _grid_positions():
        window.orchestrator.add_component(name=name, figure=name, position=(x, y))


def _remove_all(window: SetupWindow) -> None:
    for name in list(window.orchestrator.components.keys()):
        window.orchestrator.remove_component(name)


class TestAllComponents:

    # ── add ────────────────────────────────────────────────────────────────

    def test_all_components_added_to_orchestrator(
        self, window: SetupWindow, screenshot
    ):
        screenshot(window, "initial")
        _add_all(window)
        screenshot(window, "all_components_added")

        categories, _ = list_components()
        all_names = [name for names in categories.values() for name in names]
        for name in all_names:
            assert (
                name in window.orchestrator.components
            ), f"Component '{name}' missing from orchestrator.components"

    def test_all_components_graph_items_in_scene(self, window: SetupWindow, screenshot):
        _add_all(window)
        screenshot(window, "scene_after_all_added")

        scene_items = set(window.scene_attribute.items())
        for name in window.orchestrator.components:
            component = window.orchestrator.components[name]
            assert (
                component.graph in scene_items
            ), f"Graph item for '{name}' not found in scene"

    def test_component_count_matches_registry(self, window: SetupWindow):
        categories, _ = list_components()
        expected_count = sum(len(names) for names in categories.values())

        _add_all(window)

        assert len(window.orchestrator.components) == expected_count

    # ── remove ─────────────────────────────────────────────────────────────

    def test_all_components_removed_from_orchestrator(
        self, window: SetupWindow, screenshot
    ):
        _add_all(window)
        screenshot(window, "before_remove")

        _remove_all(window)
        screenshot(window, "after_remove")

        assert len(window.orchestrator.components) == 0

    def test_all_components_graph_items_removed_from_scene(
        self, window: SetupWindow, screenshot
    ):
        _add_all(window)
        graph_items = [
            window.orchestrator.components[name].graph
            for name in window.orchestrator.components
        ]

        _remove_all(window)
        screenshot(window, "scene_after_all_removed")

        scene_items = set(window.scene_attribute.items())
        for item in graph_items:
            assert item not in scene_items

    def test_remove_nonexistent_component_is_handled(self, window: SetupWindow):
        window.orchestrator.remove_component("NoSuchComponent")
        assert "NoSuchComponent" not in window.orchestrator.components
