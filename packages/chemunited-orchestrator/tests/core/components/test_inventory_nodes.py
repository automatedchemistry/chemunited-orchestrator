from chemunited_core.components import ComponentData, VesselComponentData, VesselMode
from chemunited_core.components.internals import (
    DEFAULT_INVENTORY_KEY,
    InventoryNode,
)
from chemunited_quantities import ChemUnitQuantity


def qty(value: str) -> ChemUnitQuantity:
    return ChemUnitQuantity(value)


def test_component_inventory_alias_maps_to_default_inventory():
    component = ComponentData(name="Base")

    assert component.internal_inventories == {}
    assert component.internal_inventory is None

    inventory = InventoryNode()
    component.internal_inventory = inventory

    assert component.internal_inventories == {DEFAULT_INVENTORY_KEY: inventory}
    assert component.internal_inventory is inventory

    component.internal_inventory = None

    assert component.internal_inventories == {}
    assert component.internal_inventory is None


def test_component_inventory_alias_returns_first_inserted_inventory():
    component = ComponentData(name="Tray")
    a1_inventory = InventoryNode()
    a2_inventory = InventoryNode()

    component.internal_inventories = {
        "A1": a1_inventory,
        "A2": a2_inventory,
    }

    assert component.internal_inventory is a1_inventory


def test_vessel_uses_named_default_inventory():
    vessel = VesselComponentData.from_mode(
        VesselMode(
            name="Receiver",
            capacity=qty("250 ml"),
            top_access=1,
            bottom_access=1,
        )
    )

    assert list(vessel.internal_inventories) == [DEFAULT_INVENTORY_KEY]
    assert (
        vessel.internal_inventory is vessel.internal_inventories[DEFAULT_INVENTORY_KEY]
    )
    assert set(vessel.internal_edges) == {
        (1, DEFAULT_INVENTORY_KEY),
        (2, DEFAULT_INVENTORY_KEY),
    }

    vessel.update(VesselMode(capacity=qty("100 ml")))

    assert (
        vessel.internal_inventories[DEFAULT_INVENTORY_KEY].gas_content.volume
        == qty("100 ml").to_base_units().magnitude
    )
