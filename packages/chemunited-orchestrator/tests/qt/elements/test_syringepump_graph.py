from __future__ import annotations

import pytest
from chemunited_core.common.enums import PhaseKind
from chemunited_core.components.internals import InventoryNode
from chemunited_core.compounds import VolumeContentBase
from chemunited_core.figure_registry.pumps import SyringePumpData
from pytestqt.qtbot import QtBot

from chemunited.elements.component.component_factory import create_component
from chemunited.elements.component.glossary.pumps.syringepump_graph import (
    SyringePump,
    _get_fill_level,
)


def _pump_with_fill(fraction: float) -> SyringePumpData:
    pump = SyringePumpData(name="Pump1")
    capacity_m3 = pump.syringe_volume.to_base_units().magnitude
    pump.internal_inventories["Inventory"] = InventoryNode(
        liq_content=VolumeContentBase(
            phase_kind=PhaseKind.LIQUID, volume=capacity_m3 * fraction
        ),
    )
    return pump


class TestGetFillLevel:
    def test_zero_with_no_inventory(self) -> None:
        assert _get_fill_level(SyringePumpData(name="Pump1")) == 0.0

    def test_reads_syringe_volume_as_capacity(self) -> None:
        # Regression: capacity_value doesn't exist anywhere in SyringePumpData's
        # hierarchy - the real capacity field is syringe_volume (a ChemUnitQuantity
        # needing unit conversion), not a plain float attribute.
        assert _get_fill_level(_pump_with_fill(0.3)) == 0.3

    def test_clamped_to_one_when_overfull(self) -> None:
        pump = _pump_with_fill(1.5)
        assert _get_fill_level(pump) == 1.0

    def test_zero_when_syringe_volume_missing(self) -> None:
        pump = _pump_with_fill(0.5)
        pump.syringe_volume = None  # type: ignore[assignment]
        assert _get_fill_level(pump) == 0.0


class TestSyncVisualsPlungerPosition:
    def test_plunger_position_is_absolute_across_repeated_calls(
        self, qtbot: QtBot
    ) -> None:
        component = create_component("SyringePump", name="Pump1", position=(0.0, 0.0))
        graph: SyringePump = component.graph  # type: ignore[assignment]

        base_x = graph._plunger_base_pos.x()
        base_y = graph._plunger_base_pos.y()

        graph._data.internal_inventories.update(
            _pump_with_fill(0.5).internal_inventories
        )
        graph.sync_visuals()
        pos_at_half = graph._syringe_plunger.pos()
        expected_half_x = base_x + graph.plunger_x_empty + graph.plunger_dx_full * 0.5
        assert pos_at_half.x() == pytest.approx(expected_half_x)
        assert pos_at_half.y() == pytest.approx(base_y + graph.plunger_y)

        # Regression: moveBy() is a relative move - calling sync_visuals() again
        # must not accumulate on top of the previous position.
        graph._data.internal_inventories.update(
            _pump_with_fill(0.2).internal_inventories
        )
        graph.sync_visuals()
        pos_at_fifth = graph._syringe_plunger.pos()
        expected_fifth_x = base_x + graph.plunger_x_empty + graph.plunger_dx_full * 0.2
        assert pos_at_fifth.x() == pytest.approx(expected_fifth_x)

    def test_build_places_plunger_relative_to_svg_centering_baseline(
        self, qtbot: QtBot
    ) -> None:
        # Regression: setPos(dx, dy) must not discard the centering SvgLayer
        # applies to itself at construction (setPos(-w/2, -h/2)) - the plunger
        # is meant to sit offset from that baseline, not from the group origin.
        component = create_component("SyringePump", name="Pump1", position=(0.0, 0.0))
        graph: SyringePump = component.graph  # type: ignore[assignment]

        assert graph._plunger_base_pos.x() != 0.0 or graph._plunger_base_pos.y() != 0.0
        pos = graph._syringe_plunger.pos()
        assert pos.x() == pytest.approx(
            graph._plunger_base_pos.x() + graph.plunger_x_empty
        )
        assert pos.y() == pytest.approx(graph._plunger_base_pos.y() + graph.plunger_y)

    def test_sync_visuals_updates_content_item(self, qtbot: QtBot) -> None:
        component = create_component("SyringePump", name="Pump1", position=(0.0, 0.0))
        graph: SyringePump = component.graph  # type: ignore[assignment]

        calls: list[int] = []
        graph._syringe_content.update = lambda: calls.append(1)  # type: ignore[method-assign]

        graph.sync_visuals()

        assert calls
