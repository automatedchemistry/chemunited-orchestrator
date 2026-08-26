from chemunited_core.common.constant import ATMOSPHERE_PRESSURE_PA
from chemunited_core.components.enums import BoundaryConditionKind, PortAccess
from chemunited_core.figure_registry import COMPONENTS, get_figure_path
from chemunited_core.figure_registry.assemble import (
    Gantry1DData,
    Gantry1DMode,
    Gantry3DData,
    Gantry3DMode,
)
from chemunited_core.figure_registry.vessels import VialData, VialMode


def _open_edges(component: Gantry1DData) -> set[tuple[int, int]]:
    return {
        edge_key
        for edge_key, edge in component.internal_edges.items()
        if edge.resistance_override is None
    }


def _assert_head_is_atmospheric(component: Gantry3DData) -> None:
    boundary = component.ports_by_number[1].boundary
    assert boundary is not None
    assert boundary.kind == BoundaryConditionKind.PRESSURE
    assert boundary.value == ATMOSPHERE_PRESSURE_PA


def test_gantry_registry_uses_shared_base_figure() -> None:
    assert COMPONENTS["Gantry1D"].data_class is Gantry1DData
    assert COMPONENTS["Gantry1D"].mode_class is Gantry1DMode
    assert COMPONENTS["Gantry1D"].figure_base == "Gantry"
    assert COMPONENTS["Gantry3D"].data_class is Gantry3DData
    assert COMPONENTS["Gantry3D"].mode_class is Gantry3DMode
    assert COMPONENTS["Gantry3D"].figure_base == "Gantry"
    assert issubclass(Gantry3DData, Gantry1DData)
    assert get_figure_path("Gantry3D").name == "Gantry.svg"


def test_gantry1d_position_opens_selected_port() -> None:
    gantry = Gantry1DData.from_mode(Gantry1DMode(name="linear", position_x="3"))

    assert gantry.selected_port == 4
    assert gantry.ports_by_number[1].boundary is None
    assert _open_edges(gantry) == {(1, 4)}


def test_gantry_defaults_to_atmospheric_head_with_closed_tray_edges() -> None:
    gantry = Gantry3DData.from_mode(Gantry3DMode(name="as"))

    _assert_head_is_atmospheric(gantry)
    assert _open_edges(gantry) == set()
    assert len(gantry.internal_edges) == gantry.connections_number


def test_gantry_down_at_a1_opens_only_port_2() -> None:
    gantry = Gantry3DData.from_mode(
        Gantry3DMode(name="as", position_x="1", position_y="A", position_z="DOWN")
    )

    assert gantry.selected_port == 2
    assert gantry.ports_by_number[1].boundary is None
    assert _open_edges(gantry) == {(1, 2)}


def test_gantry_down_at_a3_opens_only_port_4() -> None:
    gantry = Gantry3DData.from_mode(
        Gantry3DMode(name="as", position_x="3", position_y="A", position_z="DOWN")
    )

    assert gantry.selected_port == 4
    assert gantry.ports_by_number[1].boundary is None
    assert _open_edges(gantry) == {(1, 4)}


def test_gantry_down_at_b1_opens_only_port_22() -> None:
    gantry = Gantry3DData.from_mode(
        Gantry3DMode(name="as", position_x="1", position_y="B", position_z="DOWN")
    )

    assert gantry.selected_port == 22
    assert gantry.ports_by_number[1].boundary is None
    assert _open_edges(gantry) == {(1, 22)}


def test_gantry_apply_set_y_position_accepts_lowercase_like_real_hardware() -> None:
    # Matches flowchem's Knauer autosampler driver, which configures its Y-axis
    # discrete positions as lowercase and normalizes case before use.
    gantry = Gantry3DData.from_mode(
        Gantry3DMode(name="as", position_x="1", position_z="DOWN")
    )

    gantry.apply("set_y_position", position="a")

    assert gantry.selected_port == 2
    assert gantry.ports_by_number[1].boundary is None
    assert _open_edges(gantry) == {(1, 2)}


def test_gantry_invalid_selected_position_keeps_head_atmospheric() -> None:
    gantry = Gantry3DData.from_mode(
        Gantry3DMode(name="as", position_x="1", position_y="C", position_z="DOWN")
    )

    assert gantry.selected_port is None
    _assert_head_is_atmospheric(gantry)
    assert _open_edges(gantry) == set()


def test_gantry_non_numeric_command_position_keeps_head_atmospheric() -> None:
    gantry = Gantry3DData.from_mode(Gantry3DMode(name="as", position_z="DOWN"))

    gantry.apply("set_x_position", position="home")

    assert gantry.selected_port is None
    _assert_head_is_atmospheric(gantry)
    assert _open_edges(gantry) == set()


def test_gantry_apply_mutates_position_and_resyncs_edges() -> None:
    gantry = Gantry3DData.from_mode(Gantry3DMode(name="as"))

    gantry.apply("set_z_position", position="DOWN")
    assert _open_edges(gantry) == {(1, 2)}
    assert gantry.ports_by_number[1].boundary is None

    gantry.apply("set_x_position", position="3")
    assert _open_edges(gantry) == {(1, 4)}

    gantry.apply("set_z_position", position="UP")
    _assert_head_is_atmospheric(gantry)
    assert _open_edges(gantry) == set()


def test_vial_array_wells_are_atmospheric_when_pressure_access_is_false() -> None:
    vial = VialData.from_mode(
        VialMode(name="tray", column=3, row=2, pressure_access=False)
    )

    assert sorted(vial.ports_by_number) == [1, 2, 3, 4, 5, 6]
    for port in vial.ports_by_number.values():
        boundary = port.boundary
        assert boundary is not None
        assert boundary.kind == BoundaryConditionKind.PRESSURE
        assert boundary.value == ATMOSPHERE_PRESSURE_PA
        assert port.access == PortAccess.BOTTOM


def test_vial_array_wells_have_no_pressure_boundary_when_pressure_access_is_true() -> (
    None
):
    vial = VialData.from_mode(
        VialMode(name="tray", column=3, row=2, pressure_access=True)
    )

    assert all(port.boundary is None for port in vial.ports_by_number.values())
