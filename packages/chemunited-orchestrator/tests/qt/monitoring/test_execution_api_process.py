from __future__ import annotations

from pydantic import AnyHttpUrl
from pytestqt.qtbot import QtBot
from qfluentwidgets import TextBrowser

from chemunited.monitoring import execution_api_process
from chemunited.monitoring.execution_api_process import (
    DEFAULT_API_PORT,
    ApiClient,
    ApiProcess,
    _api_url,
    _wait_for_api_ready,
)


def test_api_process_starts_silent_workflow_tray(
    tmp_path,
    qtbot: QtBot,
    monkeypatch,
):
    log_browser = TextBrowser()
    qtbot.addWidget(log_browser)
    api_process = ApiProcess(tmp_path, log_browser)
    started: list[tuple[str, list[str]]] = []
    loaded: list[bool] = []
    monkeypatch.setattr(
        execution_api_process,
        "_workflow_tray_executable",
        lambda: r".venv\Scripts\chemunited-workflow.exe",
    )
    monkeypatch.setattr(
        execution_api_process,
        "_is_port_in_use",
        lambda _port: False,
    )
    monkeypatch.setattr(
        execution_api_process,
        "_wait_for_api_ready",
        lambda _url: True,
    )
    monkeypatch.setattr(api_process, "_load_project", lambda: loaded.append(True))
    monkeypatch.setattr(
        api_process._process,
        "start",
        lambda program, arguments: started.append((program, list(arguments))),
    )
    monkeypatch.setattr(
        api_process._process,
        "waitForStarted",
        lambda _msecs: True,
    )

    assert api_process.start_api() is True
    assert started == [
        (
            r".venv\Scripts\chemunited-workflow.exe",
            ["serve", "--port", str(DEFAULT_API_PORT), "--tray", "--silent"],
        )
    ]
    assert loaded == [True]


def test_api_process_returns_false_when_silent_tray_not_reachable(
    tmp_path,
    qtbot: QtBot,
    monkeypatch,
):
    log_browser = TextBrowser()
    qtbot.addWidget(log_browser)
    api_process = ApiProcess(tmp_path, log_browser)

    monkeypatch.setattr(
        execution_api_process,
        "_is_port_in_use",
        lambda _port: False,
    )
    monkeypatch.setattr(
        execution_api_process,
        "_wait_for_api_ready",
        lambda _url: False,
    )
    monkeypatch.setattr(
        api_process._process,
        "start",
        lambda _program, _arguments: None,
    )
    monkeypatch.setattr(
        api_process._process,
        "waitForStarted",
        lambda _msecs: True,
    )

    assert api_process.start_api() is False


def test_api_url_joins_normalized_pydantic_urls():
    assert (
        _api_url(AnyHttpUrl(f"http://localhost:{DEFAULT_API_PORT}"), "/processes")
        == f"http://localhost:{DEFAULT_API_PORT}/processes"
    )


def test_wait_for_api_ready_waits_before_quiet_probe(monkeypatch):
    slept: list[float] = []
    requested: list[tuple[str, float]] = []

    class Response:
        status_code = 200

    class Session:
        trust_env = True

        def __init__(self):
            self.proxies = {}

        def get(self, url, timeout):
            requested.append((url, timeout))
            return Response()

    monkeypatch.setattr(execution_api_process.time, "sleep", slept.append)
    monkeypatch.setattr(execution_api_process.requests, "Session", Session)

    assert _wait_for_api_ready(
        "http://localhost:3116",
        timeout=1,
        interval=0.5,
        initial_delay=2,
    )
    assert slept == [2]
    assert requested == [("http://localhost:3116/project/", 2.0)]


def test_api_client_preserves_backend_error_detail(monkeypatch):
    class Response:
        status_code = 409
        content = b'{"detail": "A run is already active."}'

        def raise_for_status(self):
            import requests

            error = requests.HTTPError("409 conflict")
            error.response = self
            raise error

        def json(self):
            return {"detail": "A run is already active."}

    class Session:
        trust_env = True

        def __init__(self):
            self.proxies = {}

        def request(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(execution_api_process.requests, "Session", Session)
    client = ApiClient(AnyHttpUrl("http://localhost:3116"))

    result = client.post("run/", data={"protocol": "test.json"})

    assert result["status_code"] == 409
    assert result["detail"] == "A run is already active."


def test_api_process_emits_project_load_conflict(tmp_path, qtbot: QtBot):
    log_browser = TextBrowser()
    qtbot.addWidget(log_browser)
    api_process = ApiProcess(tmp_path, log_browser)
    conflict = {
        "status_code": 409,
        "detail": "Cannot switch project while a run is active.",
        "error": "conflict",
    }
    api_process.client = type(
        "Client",
        (),
        {"put": lambda *_args, **_kwargs: conflict},
    )()
    captured = []
    api_process.project_load_conflict.connect(captured.append)

    api_process._load_project()

    assert captured == [conflict]
