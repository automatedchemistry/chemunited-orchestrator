from __future__ import annotations

import pytest
from chemunited_core.compounds import COMPOUNDS, ChemicalEntity
from pytestqt.qtbot import QtBot

from chemunited.elements.reactions import ReactionDialog
from chemunited.setup import SetupWindow


@pytest.fixture
def window(qtbot: QtBot):
    COMPOUNDS.clear()
    window = SetupWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    yield window
    COMPOUNDS.clear()


def _register_species() -> None:
    COMPOUNDS.register(ChemicalEntity(name="reagent", molecular_weight=10.0))
    COMPOUNDS.register(ChemicalEntity(name="product", molecular_weight=12.0))


def _add_first_order_reaction(window: SetupWindow, target: str = "reactor"):
    return window.orchestrator.add_reaction(
        target=target,
        reaction_type="FirstOrderDecay",
        reactant="reagent",
        product="product",
        rate_constant=0.3,
        phase="LIQUID",
        delta_temperature_per_mol_converted=2.0,
    )


def test_reaction_targets_include_reactors_and_default_inventories(
    window: SetupWindow,
) -> None:
    window.orchestrator.add_component(
        name="reactor", figure="FlowReactor", position=(0.0, 0.0)
    )
    window.orchestrator.add_component(
        name="photo", figure="PhotoReactor", position=(100.0, 0.0)
    )
    window.orchestrator.add_component(
        name="vessel", figure="GlassBottle", position=(200.0, 0.0)
    )
    window.orchestrator.add_component(
        name="pump", figure="HPLCPump", position=(300.0, 0.0)
    )

    assert window.orchestrator.reaction_target_names() == [
        "reactor",
        "vessel",
        "photo",
    ]


def test_add_and_remove_reaction_updates_page(window: SetupWindow) -> None:
    _register_species()
    window.orchestrator.add_component(
        name="reactor", figure="FlowReactor", position=(0.0, 0.0)
    )

    reaction = _add_first_order_reaction(window)

    assert reaction is not None
    assert len(window.orchestrator.reactions) == 1
    assert window.reactions_widget.visible_reactions() == [
        "reactor: reagent → product (liquid, k=0.3 s⁻¹)"
    ]

    window.orchestrator.remove_reaction(0)

    assert window.orchestrator.reactions == []
    assert window.reactions_widget.visible_reactions() == []


def test_removing_target_component_removes_its_reactions(window: SetupWindow) -> None:
    _register_species()
    window.orchestrator.add_component(
        name="reactor", figure="FlowReactor", position=(0.0, 0.0)
    )
    _add_first_order_reaction(window)

    window.orchestrator.remove_component("reactor")

    assert window.orchestrator.reactions == []


def test_referenced_compound_cannot_be_removed(
    window: SetupWindow, monkeypatch
) -> None:
    _register_species()
    window.orchestrator.add_component(
        name="reactor", figure="FlowReactor", position=(0.0, 0.0)
    )
    _add_first_order_reaction(window)
    compound_list = window.compounds_widget.compound_list
    compound_list.sync()
    compound_list._select_name("reagent")
    warnings: list[str] = []
    monkeypatch.setattr(compound_list, "_show_warning", warnings.append)

    compound_list.remove_selected_compound()

    assert "reagent" in COMPOUNDS
    assert warnings == [
        "Compound 'reagent' is used by a reaction. Remove the reaction first."
    ]


def test_dialog_rejects_identical_reactant_and_product(qtbot: QtBot) -> None:
    dialog = ReactionDialog(["reactor"], ["a", "b"])
    qtbot.addWidget(dialog)
    dialog.product_combo.setCurrentText("a")

    dialog._save()

    assert dialog.get_result_instance() is None
    assert not dialog.error_label.isHidden()
