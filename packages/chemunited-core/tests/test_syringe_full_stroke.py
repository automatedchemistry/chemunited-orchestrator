"""A syringe dispenses or fills what's left, as the real pump's limit switches allow."""

import pytest

from chemunited_core.figure_registry.pumps import SyringePumpData, SyringePumpMode
from chemunited_quantities import ChemUnitQuantity


def _syringe(fill: str = "0 ml") -> SyringePumpData:
    return SyringePumpData.from_mode(
        SyringePumpMode(
            name="pump",
            syringe_volume=ChemUnitQuantity("5 ml"),
            syringe_actual_volume=ChemUnitQuantity(fill),
        )
    )


def test_infuse_all_dispenses_what_the_mode_says_is_in_the_barrel() -> None:
    pump = _syringe("2 ml")

    result = pump.apply("infuse-all")

    assert pump.flow_rate_si > 0.0
    # 2 mL at the default 10 mL/min.
    assert [(s.command, s.dt) for s in result.scheduled] == [
        ("stop", pytest.approx(12.0))
    ]


def test_infuse_all_prefers_the_live_fill_level() -> None:
    pump = _syringe("2 ml")
    pump.fill_m3 = 1.0e-6

    result = pump.apply("infuse-all")

    assert result.scheduled[0].dt == pytest.approx(6.0)


def test_infuse_all_runs_at_the_last_commanded_rate() -> None:
    pump = _syringe("2 ml")
    pump.apply("withdraw", rate="60 ml/min", volume="1 ml")
    pump.apply("stop")
    pump.fill_m3 = 3.0e-6

    result = pump.apply("infuse-all")

    assert pump.flow_rate_si == pytest.approx(1.0e-6)
    assert result.scheduled[0].dt == pytest.approx(3.0)


def test_infuse_all_on_an_empty_syringe_does_not_move() -> None:
    pump = _syringe("0 ml")

    result = pump.apply("infuse-all")

    assert pump.flow_rate_si == 0.0
    assert result.scheduled == []


def test_withdraw_all_fills_what_is_left_of_the_barrel() -> None:
    pump = _syringe("2 ml")

    result = pump.apply("withdraw-all")

    assert pump.flow_rate_si < 0.0
    # 3 mL of room at the default 10 mL/min.
    assert result.scheduled[0].dt == pytest.approx(18.0)


def test_withdraw_all_on_a_full_syringe_does_not_move() -> None:
    pump = _syringe("5 ml")

    result = pump.apply("withdraw-all")

    assert pump.flow_rate_si == 0.0
    assert result.scheduled == []


def test_full_stroke_commands_are_known_to_put() -> None:
    pump = _syringe("2 ml")

    assert pump.put("infuse-all").scheduled == []
    assert pump.put("withdraw-all").scheduled == []
