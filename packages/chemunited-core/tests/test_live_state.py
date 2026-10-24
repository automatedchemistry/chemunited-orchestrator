"""Tests for chemunited_core.components.live_state (live platform view pictures)."""

from __future__ import annotations

import json

import pytest

from chemunited_core.components.live_state import (
    LivePicture,
    UnrecognisedCommand,
    iter_apply_kwargs,
    picture_kind,
    rotor_links,
    visual_state,
)
from chemunited_core.components.valve import connection_from_rotor
from chemunited_core.figure_registry import COMPONENTS
from chemunited_core.protocols import get_protocol_class


def _make(figure: str, name: str = "dev", **kwargs):
    defn = COMPONENTS[figure]
    return defn.data_class.from_mode(defn.mode_class(name=name, **kwargs))


ROTARY_VALVES = sorted(
    figure for figure in COMPONENTS if picture_kind(_make(figure)) == "rotor"
)


def test_every_built_in_rotary_valve_has_a_rotor_picture():
    assert ROTARY_VALVES == [
        "FourPortDistributionValve",
        "FourPortFivePositionValve",
        "SixPortDistributionValve",
        "SixPortTwoPositionValve",
        "SixteenPortDistributionValve",
        "ThreePortFourPositionValve",
        "ThreePortTwoPositionValve",
        "TwelvePortDistributionValve",
        "TwoPortDistributionValve",
    ]


@pytest.mark.parametrize(
    ("figure", "kind"),
    [
        ("SolenoidValve", "solenoid"),
        ("SolenoidValve2Way", "two-way"),
        ("MFCComponent", "mfc"),
        ("MultiChannelRelay", "relay"),
        ("MultiChannelADC", None),
        ("SyringePump", None),
        ("Sink", None),
    ],
)
def test_picture_kind(figure, kind):
    assert picture_kind(_make(figure)) == kind


# ── iter_apply_kwargs ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("connect", "expected"),
    [
        ("[0, 2]", [(0, 2)]),
        ("[[0, 2]]", [(0, 2)]),
        ("[[0, 2], [3, 4]]", [(0, 2), (3, 4)]),
    ],
)
def test_iter_apply_kwargs_unwraps_every_connect_shape(connect, expected):
    calls = list(iter_apply_kwargs("position", {"connect": connect, "disconnect": ""}))
    assert calls == [{"connect": pair, "disconnect": ""} for pair in expected]


@pytest.mark.parametrize(
    ("command", "params"),
    [
        ("position", {"connect": [0, 2]}),
        ("position", {"connect": "not json"}),
        ("withdraw", {"rate": "1 ml/min"}),
    ],
)
def test_iter_apply_kwargs_passes_anything_else_through(command, params):
    assert list(iter_apply_kwargs(command, params)) == [params]


# ── RotaryValveData.apply()/put() take real position commands ───────────────


@pytest.mark.parametrize("figure", ROTARY_VALVES)
def test_apply_follows_every_position_the_protocol_offers(figure):
    valve = _make(figure)
    position = get_protocol_class(figure)("dev").commands["position"]
    options = position.model_fields["connect"].json_schema_extra["Options"]
    assert options

    for connect in options:
        valve.apply("position", connect=connect)
        (pair,) = [tuple(p) for p in json.loads(connect)]
        _, active = connection_from_rotor(valve.stator_ports, valve.rotor_ports)
        assert pair in active or pair[::-1] in active, connect
        valve.put("position", connect=connect)  # accepted, doesn't raise


def test_put_rejects_a_position_the_valve_cannot_take():
    with pytest.raises(ValueError, match="not possible"):
        _make("SixPortDistributionValve").put("position", connect="[[1, 2]]")


# ── rotor_links: what RotorChannel.paint draws ──────────────────────────────


@pytest.mark.parametrize(
    ("figure", "links"),
    [
        ("SixPortTwoPositionValve", [(1, 2), (3, 4), (5, 6)]),
        ("ThreePortTwoPositionValve", [(1, 2)]),
        ("SixPortDistributionValve", [(0, 1)]),
        ("TwoPortDistributionValve", [(0, 1)]),
        # Both hub channels are drawn: connection_from_rotor stops at the first.
        ("ThreePortFourPositionValve", [(0, 1), (0, 2), (3, 4)]),
        ("FourPortFivePositionValve", [(0, 2), (5, 7)]),
    ],
)
def test_rotor_links_in_the_design_position(figure, links):
    assert rotor_links(_make(figure)) == links


def test_rotor_links_follow_a_position_command_in_rotor_slots():
    valve = _make("SixPortDistributionValve")

    valve.apply("position", connect="[[0, 4]]")

    assert rotor_links(valve) == [(0, 4)]
    assert visual_state(valve) == {"links": [[0, 4]]}


# ── LivePicture ──────────────────────────────────────────────────────────────


def test_a_rotor_picture_follows_position_commands():
    picture = LivePicture(_make("SixPortTwoPositionValve"))

    assert picture.apply("position", {"connect": "[[2, 3]]"}) == {
        "links": [[1, 6], [2, 3], [4, 5]]
    }
    assert picture.apply("position", {"connect": "[1, 2]"}) == {
        "links": [[1, 2], [3, 4], [5, 6]]
    }


@pytest.mark.parametrize(
    ("command", "params", "reason"),
    [
        ("position", {"connect": "[[1, 2]]"}, "can't connect ports"),
        ("position", {"connect": "not json"}, "Could not apply"),
        ("position", {}, "Could not apply"),
        ("home", {}, "doesn't say"),
    ],
)
def test_a_rotor_command_that_does_not_set_a_position_is_unrecognised(
    command, params, reason
):
    picture = LivePicture(_make("SixPortDistributionValve", name="Reagent valve"))

    with pytest.raises(UnrecognisedCommand, match=reason):
        picture.apply(command, params)


@pytest.mark.parametrize(
    ("command", "normally_open", "opened"),
    [
        ("open", True, True),
        ("close", True, False),
        ("power-on", True, False),
        ("power-off", True, True),
        ("power-on", False, True),
    ],
)
def test_a_solenoid_picture(command, normally_open, opened):
    picture = LivePicture(_make("SolenoidValve", normally_open=normally_open))
    assert picture.apply(command) == {"open": opened}


def test_a_two_way_solenoid_shows_its_position():
    picture = LivePicture(_make("SolenoidValve2Way"))
    assert picture.apply("close") == {"position": 2}
    assert picture.apply("open") == {"position": 1}


def test_an_mfc_is_active_while_it_has_a_flow_rate():
    picture = LivePicture(_make("MFCComponent"))
    assert picture.apply("set-flow-rate", {"flowrate": "1.5 ml/min"}) == {
        "active": True
    }
    assert picture.apply("stop") == {"active": False}
    with pytest.raises(UnrecognisedCommand):
        picture.apply("set-flow-rate", {})


def test_relay_channels_nothing_has_switched_yet_stay_unknown():
    picture = LivePicture(_make("MultiChannelRelay", channels=4))

    assert picture.apply("power-on", {"channel": "3"}) == {
        "channels": [None, None, True, None]
    }
    assert picture.apply("power-off", {"channel": 1}) == {
        "channels": [False, None, True, None]
    }
    assert picture.apply("multiple_channel", {"values": "0201"}) == {
        "channels": [False, True, False, True]
    }


@pytest.mark.parametrize("params", [{"channel": "9"}, {"channel": "x"}, {}])
def test_a_relay_command_for_a_missing_channel_is_unrecognised(params):
    picture = LivePicture(_make("MultiChannelRelay", channels=4))
    with pytest.raises(UnrecognisedCommand, match="no channel"):
        picture.apply("power-on", params)


def test_a_device_without_a_picture_recognises_nothing():
    picture = LivePicture(_make("Sink"))
    assert picture.kind is None
    with pytest.raises(UnrecognisedCommand):
        picture.apply("open")
