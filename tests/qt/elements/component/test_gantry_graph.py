from chemunited.elements.component.component_factory import (
    create_component,
    list_components,
)
from chemunited.elements.component.component_parts import TextElement
from chemunited.elements.component.glossary.assembly.gantry_graph import (
    Gantry1D,
    Gantry3D,
)


def test_gantries_use_custom_graph_components():
    _, components = list_components()

    assert components["Gantry1D"] is Gantry1D
    assert components["Gantry3D"] is Gantry3D


def _labels_for(figure: str) -> list[str]:
    component = create_component(
        figure,
        name="gantry",
        connections_number=6,
    )
    return [
        item.toPlainText()
        for item in component.graph.childItems()
        if isinstance(item, TextElement)
    ]


def test_gantry1d_shows_characteristic_label(qapp):
    assert "1D" in _labels_for("Gantry1D")


def test_gantry3d_shows_characteristic_label(qapp):
    assert "3D" in _labels_for("Gantry3D")
