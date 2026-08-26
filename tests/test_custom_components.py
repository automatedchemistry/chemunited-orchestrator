"""Tests for project-local custom component/protocol registration.

See chemunited_core.figure_registry.register_component,
chemunited_core.figure_registry.project_loader.load_project_components, and
chemunited_core.protocols.register_protocol.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chemunited_core.components import ComponentData, ComponentMode
from chemunited_core.figure_registry import (
    COMPONENTS,
    ComponentDefinition,
    clear_project_components,
    get_figure_path,
    get_figure_svg,
    is_project_component,
    list_figures,
    register_component,
    register_figure,
)
from chemunited_core.figure_registry.project_loader import load_project_components
from chemunited_core.protocols import (
    CommandSignature,
    ComponentProtocol,
    HPLCPumpProtocols,
    clear_project_protocols,
    get_protocol_class,
    register_protocol,
)

FIXTURE_SVG = Path(__file__).parent / "_CustomFixtureFigure.svg"


class _CustomMode(ComponentMode):
    pass


class _CustomData(ComponentData):
    pass


@pytest.fixture(autouse=True)
def _reset_project_registries():
    clear_project_components()
    clear_project_protocols()
    yield
    clear_project_components()
    clear_project_protocols()
    FIXTURE_SVG.unlink(missing_ok=True)


# ── register_component ──────────────────────────────────────────────────────


def test_register_component_adds_to_components() -> None:
    register_component(
        "_TestCustomComponent", ComponentDefinition(_CustomData, _CustomMode)
    )

    assert "_TestCustomComponent" in COMPONENTS
    assert is_project_component("_TestCustomComponent")
    assert not is_project_component("Vial")


def test_register_component_rejects_duplicate_without_override() -> None:
    register_component(
        "_TestCustomComponent", ComponentDefinition(_CustomData, _CustomMode)
    )

    with pytest.raises(ValueError, match="already registered"):
        register_component(
            "_TestCustomComponent", ComponentDefinition(_CustomData, _CustomMode)
        )


def test_register_component_rejects_builtin_name_clash() -> None:
    with pytest.raises(ValueError, match="already registered"):
        register_component("Vial", ComponentDefinition(_CustomData, _CustomMode))


def test_register_component_override_replaces_existing() -> None:
    register_component(
        "_TestCustomComponent", ComponentDefinition(_CustomData, _CustomMode)
    )
    register_component(
        "_TestCustomComponent",
        ComponentDefinition(_CustomData, _CustomMode, category="custom"),
        override=True,
    )

    assert COMPONENTS["_TestCustomComponent"].category == "custom"


def test_register_component_auto_resolves_figure_next_to_caller() -> None:
    FIXTURE_SVG.write_text("<svg>fixture</svg>", encoding="utf-8")

    register_component(
        "_TestCustomComponent",
        ComponentDefinition(
            _CustomData, _CustomMode, figure_base="_CustomFixtureFigure"
        ),
    )

    assert get_figure_svg("_CustomFixtureFigure") == "<svg>fixture</svg>"
    assert get_figure_path("_CustomFixtureFigure").read_text() == "<svg>fixture</svg>"
    assert "_CustomFixtureFigure" in list_figures()


def test_register_component_explicit_figure_path(tmp_path: Path) -> None:
    svg_path = tmp_path / "Whatever.svg"
    svg_path.write_text("<svg>explicit</svg>", encoding="utf-8")

    register_component(
        "_TestCustomComponent",
        ComponentDefinition(_CustomData, _CustomMode),
        figure_path=svg_path,
    )

    assert get_figure_svg("_TestCustomComponent") == "<svg>explicit</svg>"


def test_register_component_without_matching_svg_leaves_builtin_figures_untouched() -> (
    None
):
    register_component(
        "_TestCustomComponent",
        ComponentDefinition(_CustomData, _CustomMode, figure_base="Vial"),
    )

    # No "_CustomFixtureFigure.svg"/"Vial.svg" next to this test file, so no
    # external override is recorded and the built-in "Vial" figure is unaffected.
    assert get_figure_svg("Vial") == get_figure_path("Vial").read_text()


def test_clear_project_components_removes_only_project_entries() -> None:
    register_component(
        "_TestCustomComponent", ComponentDefinition(_CustomData, _CustomMode)
    )
    assert "_TestCustomComponent" in COMPONENTS

    clear_project_components()

    assert "_TestCustomComponent" not in COMPONENTS
    assert "Vial" in COMPONENTS


# ── register_protocol / get_protocol_class ──────────────────────────────────


def test_register_protocol_and_get_protocol_class() -> None:
    class _PingCommand(CommandSignature):
        command: str = "ping"

    class _CustomProtocols(ComponentProtocol):
        def __init__(self, name: str) -> None:
            super().__init__(name)
            self.commands["ping"] = _PingCommand

    register_protocol("_TestCustomComponent", _CustomProtocols)

    assert get_protocol_class("_TestCustomComponent") is _CustomProtocols


def test_register_protocol_rejects_duplicate_without_override() -> None:
    class _CustomProtocols(ComponentProtocol):
        pass

    register_protocol("_TestCustomComponent", _CustomProtocols)

    with pytest.raises(ValueError, match="already registered"):
        register_protocol("_TestCustomComponent", _CustomProtocols)


def test_get_protocol_class_falls_back_to_builtin() -> None:
    assert get_protocol_class("HPLCPump") is HPLCPumpProtocols


def test_get_protocol_class_falls_back_to_generic_for_unknown_figure() -> None:
    assert get_protocol_class("_TotallyUnknownFigure") is ComponentProtocol


# ── load_project_components ─────────────────────────────────────────────────


def _write_my_thing_component(project_dir: Path) -> None:
    components_dir = project_dir / "customizations" / "components"
    components_dir.mkdir(parents=True)
    (components_dir / "__init__.py").write_text(
        "from . import my_thing\n", encoding="utf-8"
    )
    (components_dir / "my_thing.py").write_text(
        "from chemunited_core.components import ComponentData, ComponentMode\n"
        "from chemunited_core.figure_registry import (\n"
        "    ComponentDefinition,\n"
        "    register_component,\n"
        ")\n"
        "\n"
        "class MyThingMode(ComponentMode):\n"
        "    pass\n"
        "\n"
        "class MyThingData(ComponentData):\n"
        "    pass\n"
        "\n"
        "register_component(\n"
        "    'MyThing', ComponentDefinition(MyThingData, MyThingMode)\n"
        ")\n",
        encoding="utf-8",
    )


def test_load_project_components_imports_components_package(tmp_path: Path) -> None:
    _write_my_thing_component(tmp_path)

    registered = load_project_components(tmp_path)

    assert registered == ["MyThing"]
    assert "MyThing" in COMPONENTS
    assert is_project_component("MyThing")


def test_load_project_components_no_components_folder_is_noop(tmp_path: Path) -> None:
    assert load_project_components(tmp_path) == []


def test_load_project_components_can_be_reloaded_without_error(tmp_path: Path) -> None:
    """Re-opening the same (or a different) project must not hit a stale
    'already registered' clash from a previous load."""
    _write_my_thing_component(tmp_path)

    first = load_project_components(tmp_path)
    second = load_project_components(tmp_path)

    assert first == second == ["MyThing"]


# ── register_figure / auxiliary composited-layer SVGs ───────────────────────


def test_register_figure_makes_svg_resolvable() -> None:
    fixture = Path(__file__).parent / "_AuxiliaryFixtureLayer.svg"
    fixture.write_text("<svg>aux</svg>", encoding="utf-8")
    try:
        register_figure("AuxiliaryLayer", fixture)

        assert get_figure_svg("AuxiliaryLayer") == "<svg>aux</svg>"
        assert "AuxiliaryLayer" in list_figures()
    finally:
        fixture.unlink(missing_ok=True)


def test_register_figure_rejects_duplicate_without_override() -> None:
    register_figure("_TestAuxLayer", Path("whatever.svg"))

    with pytest.raises(ValueError, match="already registered"):
        register_figure("_TestAuxLayer", Path("other.svg"))


def test_load_project_components_discovers_auxiliary_layer_svgs(
    tmp_path: Path,
) -> None:
    """An SVG referenced ad hoc from a custom GraphComponent.build() (e.g.
    self._build_svg("ExtraLayer")) has no register_component() call of its
    own — load_project_components() must still make it discoverable just by
    being present in customizations/components/."""
    _write_my_thing_component(tmp_path)
    (tmp_path / "customizations" / "components" / "ExtraLayer.svg").write_text(
        "<svg>extra layer</svg>", encoding="utf-8"
    )

    load_project_components(tmp_path)

    assert get_figure_svg("ExtraLayer") == "<svg>extra layer</svg>"
