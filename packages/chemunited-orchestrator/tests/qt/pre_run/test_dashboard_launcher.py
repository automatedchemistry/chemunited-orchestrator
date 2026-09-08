from __future__ import annotations

from typing import cast

from PyQt5.QtWidgets import QLineEdit
from pytestqt.qtbot import QtBot

from chemunited.pre_run import dashboard_launcher
from chemunited.pre_run.dashboard_launcher import DashBoardLauncherFrame


def _make_frame(qtbot: QtBot, monkeypatch) -> DashBoardLauncherFrame:
    monkeypatch.setattr(
        dashboard_launcher, "inpect_execution_address", lambda *a, **k: False
    )
    frame = DashBoardLauncherFrame(None)  # type: ignore[arg-type]
    qtbot.addWidget(frame)
    frame.show()
    qtbot.waitExposed(frame)
    return frame


def test_advertise_toggle_reveals_and_generates_token(
    qtbot: QtBot, monkeypatch, screenshot
):
    frame = _make_frame(qtbot, monkeypatch)

    assert not frame._advertise_token_row.isVisible()
    assert frame._token_edit.text() == ""

    frame._advertise_switch.setChecked(True)
    frame.resize(620, 950)
    screenshot(frame, "advertise_on_with_token")

    assert frame._advertise_token_row.isVisible()
    token = frame._token_edit.text()
    assert len(token) > 20
    assert frame._token_edit.echoMode() == QLineEdit.Password
    assert token not in frame._command_preview.text()
    assert frame._token_env_note.isVisible()
    assert "CHEMUNITED_API_TOKEN" in frame._token_env_note.text()

    frame._advertise_switch.setChecked(False)
    assert not frame._advertise_token_row.isVisible()
    frame._advertise_switch.setChecked(True)
    assert frame._token_edit.text() == token


def test_empty_token_shows_warning_note(qtbot: QtBot, monkeypatch):
    frame = _make_frame(qtbot, monkeypatch)

    frame._advertise_switch.setChecked(True)
    frame._token_edit.clear()

    assert frame._token_env_note.isVisible()
    assert "Warning" in frame._token_env_note.text()


def test_launch_passes_token_via_env_not_args(qtbot: QtBot, monkeypatch):
    frame = _make_frame(qtbot, monkeypatch)
    frame._advertise_switch.setChecked(True)
    token = frame._token_edit.text()

    captured: dict[str, list[str] | dict[str, str] | None] = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env")
        return object()

    monkeypatch.setattr(dashboard_launcher.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        dashboard_launcher.importlib.util, "find_spec", lambda name: object()
    )

    frame._launch_dashboard()

    assert token not in cast("list[str]", captured["args"])
    env = cast("dict[str, str]", captured["env"])
    assert env["CHEMUNITED_API_TOKEN"] == token
    assert frame._launched_token == token


def test_launch_without_advertise_leaves_env_untouched(qtbot: QtBot, monkeypatch):
    frame = _make_frame(qtbot, monkeypatch)

    captured: dict[str, dict[str, str] | None] = {}

    def fake_popen(args, **kwargs):
        captured["env"] = kwargs.get("env")
        return object()

    monkeypatch.setattr(dashboard_launcher.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        dashboard_launcher.importlib.util, "find_spec", lambda name: object()
    )

    frame._launch_dashboard()

    assert captured["env"] is None
    assert frame._launched_token is None
