from __future__ import annotations

import sys

from chemunited_core.common.enums import ConnectionType, PhaseKind
from chemunited_core.components import ComponentData
from chemunited_core.compounds import COMPOUNDS, ChemicalEntity, VolumeContentBase
from chemunited_core.connections import EdgeData
from chemunited_quantities import ChemUnitQuantity
from PyQt5.QtWidgets import QApplication

from chemunited.elements.component.graph_item import GraphComponent
from chemunited.elements.connection.connection import HydraulicConnectionItem
from chemunited.shared.graph import GraphCore, SceneCore


def _register_demo_compounds() -> None:
    COMPOUNDS.register(
        ChemicalEntity(
            name="violet_dye",
            color_red=140,
            color_green=30,
            color_blue=200,
            color_alpha=255,
        )
    )
    COMPOUNDS.register(
        ChemicalEntity(
            name="blue_dye",
            color_red=30,
            color_green=100,
            color_blue=255,
            color_alpha=255,
        )
    )
    COMPOUNDS.register(
        ChemicalEntity(
            name="green_dye",
            color_red=30,
            color_green=200,
            color_blue=60,
            color_alpha=255,
        )
    )
    COMPOUNDS.register(
        ChemicalEntity(
            name="yellow_dye",
            color_red=230,
            color_green=200,
            color_blue=20,
            color_alpha=255,
        )
    )
    COMPOUNDS.register(
        ChemicalEntity(
            name="red_dye",
            color_red=220,
            color_green=30,
            color_blue=30,
            color_alpha=255,
        )
    )


def _demo_content() -> list[VolumeContentBase]:
    # EdgeData.content is stored destination-first (content[0] = destination-side,
    # content[-1] = origin-side), so this list has to be built in that order to
    # render "violet, blue, green, yellow, red" walking origin -> destination.
    return [
        VolumeContentBase(  # destination-side
            phase_kind=PhaseKind.LIQUID,
            volume=2.0e-8,
            initial_species={"red_dye": 1.0},
        ),
        VolumeContentBase(
            phase_kind=PhaseKind.LIQUID,
            volume=5.0e-8,
            initial_species={"yellow_dye": 1.0},
        ),
        VolumeContentBase(  # middle: largest slug
            phase_kind=PhaseKind.LIQUID,
            volume=1.2e-7,
            initial_species={"green_dye": 1.0},
        ),
        VolumeContentBase(
            phase_kind=PhaseKind.LIQUID,
            volume=5.0e-8,
            initial_species={"blue_dye": 1.0},
        ),
        VolumeContentBase(  # origin-side
            phase_kind=PhaseKind.LIQUID,
            volume=2.0e-8,
            initial_species={"violet_dye": 1.0},
        ),
    ]


def main() -> None:
    app = QApplication(sys.argv)
    _register_demo_compounds()
    scene = SceneCore()
    component = GraphComponent(data=ComponentData())
    scene.addItem(component)
    component2 = GraphComponent(data=ComponentData())
    scene.addItem(component2)
    component.setPos(100, 10)
    connection = HydraulicConnectionItem(
        origin_port=component._points[1],
        destination_port=component2._points[2],
        data=EdgeData(
            origin="a",
            destination="b",
            origin_port=1,
            destination_port=2,
            classification=ConnectionType.HYDRAULIC,
            length=ChemUnitQuantity("100 mm"),
            diameter=ChemUnitQuantity("2 mm"),
            content=_demo_content(),
        ),
    )
    scene.addItem(connection)
    view = GraphCore(scene)
    view.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
