from __future__ import annotations

from types import SimpleNamespace

from pydantic import AnyHttpUrl
from pytestqt.qtbot import QtBot
from qfluentwidgets import TextBrowser

from chemunited.qt.monitoring import execution_api_process
from chemunited.qt.monitoring.execution_api_process import (
    DEFAULT_API_PORT,
    ApiProcess,
    _api_url,
)


def test_api_process_starts_venv_workflow_cli(tmp_path, qtbot: QtBot, monkeypatch):
    log_browser = TextBrowser()
    qtbot.addWidget(log_browser)
    api_process = ApiProcess(tmp_path, log_browser)
    started: list[tuple[str, list[str]]] = []

    class AcceptedDialog:
        Accepted = 1

        def __init__(self, parent=None):
            pass

        def exec(self):
            return self.Accepted

        def get_result_instance(self):
            return SimpleNamespace(
                already_running=False,
                address=AnyHttpUrl(f"http://localhost:{DEFAULT_API_PORT}"),
            )

    monkeypatch.setattr(execution_api_process, "APIDialog", AcceptedDialog)
    monkeypatch.setattr(
        execution_api_process,
        "_workflow_cli_executable",
        lambda: r".venv\Scripts\chemunited-workflow.exe",
    )
    monkeypatch.setattr(
        api_process._process,
        "start",
        lambda program, arguments: started.append((program, list(arguments))),
    )

    assert api_process.start_api() is True
    assert started == [
        (
            r".venv\Scripts\chemunited-workflow.exe",
            [str(tmp_path), "--fastapi", "--port", str(DEFAULT_API_PORT)],
        )
    ]


def test_api_url_joins_normalized_pydantic_urls():
    assert (
        _api_url(AnyHttpUrl(f"http://localhost:{DEFAULT_API_PORT}"), "/processes")
        == f"http://localhost:{DEFAULT_API_PORT}/processes"
    )
