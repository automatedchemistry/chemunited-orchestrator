from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from loguru import logger
from PyQt5.QtWidgets import QLineEdit
from pytestqt.qtbot import QtBot

from chemunited.pre_run import dashboard_launcher
from chemunited.pre_run.dashboard_launcher import DashBoardLauncherFrame


@pytest.fixture(autouse=True)
def _isolated_launcher(monkeypatch, tmp_path):
    """Never reach a real dashboard, browser or server log from these tests.

    Registered on the shared monkeypatch, so the patches outlive the
    conftest's teardown wait, during which a launch's poll timer can fire.
    """
    monkeypatch.setattr(dashboard_launcher, "_dashboard_answers", lambda port: False)
    monkeypatch.setattr(dashboard_launcher.webbrowser, "open", lambda url: True)
    monkeypatch.setattr(dashboard_launcher, "SERVER_LOG", tmp_path / "server.log")


def _make_frame(qtbot: QtBot, monkeypatch) -> DashBoardLauncherFrame:
    monkeypatch.setattr(
        dashboard_launcher, "inpect_execution_address", lambda *a, **k: False
    )
    frame = DashBoardLauncherFrame(None)  # type: ignore[arg-type]
    qtbot.addWidget(frame)
    frame.show()
    qtbot.waitExposed(frame)
    return frame


def _fake_launch(monkeypatch, *, exit_code: int | None = None) -> dict:
    """Make Launch record its Popen call; the child reports *exit_code*."""
    captured: dict = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs.get("env")
        captured["stderr"] = kwargs.get("stderr")
        return SimpleNamespace(poll=lambda: exit_code)

    monkeypatch.setattr(dashboard_launcher.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        dashboard_launcher.importlib.util, "find_spec", lambda name: object()
    )
    return captured


def test_advertise_toggle_reveals_and_generates_token(qtbot: QtBot, monkeypatch):
    frame = _make_frame(qtbot, monkeypatch)

    assert not frame._advertise_token_row.isVisible()
    assert frame._token_edit.text() == ""

    frame._advertise_switch.setChecked(True)
    frame.resize(620, 950)

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
    captured = _fake_launch(monkeypatch)

    frame._launch_dashboard()

    assert token not in cast("list[str]", captured["args"])
    env = cast("dict[str, str]", captured["env"])
    assert env["CHEMUNITED_API_TOKEN"] == token
    assert frame._launched_token == token


def test_launch_without_advertise_leaves_env_untouched(qtbot: QtBot, monkeypatch):
    frame = _make_frame(qtbot, monkeypatch)
    captured = _fake_launch(monkeypatch)

    frame._launch_dashboard()

    assert captured["env"] is None
    assert frame._launched_token is None


def test_launch_loads_the_open_project(qtbot: QtBot, monkeypatch, tmp_path):
    frame = _make_frame(qtbot, monkeypatch)
    serve = [sys.executable, "-m", "chemunited_workflow.cli", "serve"]

    assert frame._build_args()[:4] == serve
    assert str(tmp_path) not in frame._build_args()

    monkeypatch.setattr(frame, "_project_dir", lambda: tmp_path)
    frame.sync()

    assert frame._build_args()[:5] == [*serve, str(tmp_path)]
    assert str(tmp_path) in frame._command_preview.text()


def test_launch_opens_the_dashboard_once_it_answers(
    qtbot: QtBot, monkeypatch, tmp_path
):
    frame = _make_frame(qtbot, monkeypatch)
    monkeypatch.setattr(frame, "_project_dir", lambda: tmp_path)
    # A silent launch exits 0 once the detached server is started.
    captured = _fake_launch(monkeypatch, exit_code=0)
    opened: list[str] = []
    monkeypatch.setattr(dashboard_launcher.webbrowser, "open", opened.append)

    frame._launch_dashboard()

    assert str(tmp_path) in captured["args"]
    assert frame._status_badge._label.text() == "Starting…"
    assert not frame._launch_btn.isEnabled()
    frame._poll_ready()
    assert frame._is_starting
    assert opened == []

    monkeypatch.setattr(
        dashboard_launcher, "inpect_execution_address", lambda *a, **k: True
    )
    monkeypatch.setattr(dashboard_launcher, "_dashboard_answers", lambda port: True)
    qtbot.waitUntil(lambda: bool(opened), timeout=3000)

    assert opened == [f"http://127.0.0.1:{dashboard_launcher.DEFAULT_PORT}/"]
    assert frame._is_running
    assert not frame._is_starting
    assert frame._status_badge._label.text() == "Running"


def test_launch_gives_up_when_the_server_exits(qtbot: QtBot, monkeypatch):
    frame = _make_frame(qtbot, monkeypatch)
    _fake_launch(monkeypatch, exit_code=2)
    opened: list[str] = []
    monkeypatch.setattr(dashboard_launcher.webbrowser, "open", opened.append)
    errors: list[str] = []
    sink = logger.add(lambda m: errors.append(m.record["message"]), level="ERROR")

    try:
        frame._launch_dashboard()
        frame._poll_ready()
    finally:
        logger.remove(sink)

    assert not frame._is_starting
    assert not frame._is_running
    assert frame._status_badge._label.text() == "Not Running"
    assert frame._launch_btn.isEnabled()
    assert opened == []
    assert "exited with code 2" in errors[0]
    assert str(dashboard_launcher.SERVER_LOG) in errors[0]


def test_launch_gives_up_after_the_timeout(qtbot: QtBot, monkeypatch):
    frame = _make_frame(qtbot, monkeypatch)
    _fake_launch(monkeypatch)
    monkeypatch.setattr(dashboard_launcher, "READY_TIMEOUT_S", 0.0)
    opened: list[str] = []
    monkeypatch.setattr(dashboard_launcher.webbrowser, "open", opened.append)

    frame._launch_dashboard()
    frame._poll_ready()

    assert not frame._is_starting
    assert not frame._is_running
    assert opened == []


def test_non_silent_launch_sends_errors_to_the_server_log(qtbot: QtBot, monkeypatch):
    frame = _make_frame(qtbot, monkeypatch)
    frame._tray_switch.setChecked(False)  # also turns Silent off
    captured = _fake_launch(monkeypatch)

    frame._launch_dashboard()

    assert "--silent" not in captured["args"]
    assert Path(captured["stderr"].name) == dashboard_launcher.SERVER_LOG
    assert captured["stderr"].closed
