from __future__ import annotations

import json
from types import SimpleNamespace

from chemunited_workflow.api.schemas import RunStatus
from loguru import logger

from chemunited.qt.orchestrator.execution import (
    OrchestratorExecution,
    RunPollingThread,
    _incremental_text,
    _process_name_from_protocol_key,
    _validate_model,
)
from chemunited.qt.shared.enums import WindowCategory


def test_process_name_from_protocol_key_uses_file_stem() -> None:
    assert _process_name_from_protocol_key("clean_0") == "clean"
    assert _process_name_from_protocol_key("my_process_12") == "my_process"
    assert _process_name_from_protocol_key("ReactProcess_1") == "ReactProcess"
    assert _process_name_from_protocol_key("main_parameter") is None
    assert _process_name_from_protocol_key("ReactProcess") is None
    assert _process_name_from_protocol_key("React_x") is None


def test_set_project_protocol_script_dir_activates_saved_process_names(
    tmp_path,
) -> None:
    path = tmp_path / "protocol.json"
    path.write_text(
        json.dumps(
            {
                "main_parameter": {},
                "clean_0": {},
                "ReactProcess_1": {},
                "my_process_2": {},
                "malformed": {},
            }
        ),
        encoding="utf-8",
    )

    class ProtocolsWidget:
        def __init__(self) -> None:
            self.activated: list[str] = []

        def activate_process(self, process_name: str) -> None:
            self.activated.append(process_name)

    protocols_widget = ProtocolsWidget()
    selected: list[str] = []
    execution = OrchestratorExecution.__new__(OrchestratorExecution)
    execution.parent_ref = SimpleNamespace(protocols_widget=protocols_widget)
    execution.select_process = selected.append

    execution.set_project_protocol_script_dir(path)

    assert protocols_widget.activated == ["clean", "ReactProcess", "my_process"]
    assert selected == ["clean"]


class FakeClient:
    def __init__(self, post_response=None, delete_response=None, get_response=None):
        self.post_response = post_response
        self.delete_response = delete_response
        self.get_response = get_response
        self.gets: list[str] = []
        self.posts: list[tuple[str, dict | None]] = []
        self.deletes: list[str] = []

    def get(self, endpoint: str, params: dict | None = None, timeout: int = 10):
        self.gets.append(endpoint)
        return self.get_response

    def post(self, endpoint: str, data: dict | None = None, timeout: int = 10):
        self.posts.append((endpoint, data))
        return self.post_response

    def delete(self, endpoint: str, timeout: int = 10):
        self.deletes.append(endpoint)
        return self.delete_response


def _execution_with_parent(client: FakeClient, *, online: bool = True):
    execution = OrchestratorExecution.__new__(OrchestratorExecution)
    execution.parent_ref = SimpleNamespace(
        status_widget=SimpleNamespace(text=lambda: "Online" if online else "Offline"),
        api_process=SimpleNamespace(client=client),
    )
    execution.active_run_id = None
    execution._run_polling_thread = None
    execution._start_run_polling = lambda _client, _run_id: None
    return execution


def test_execute_returns_false_when_offline(tmp_path) -> None:
    client = FakeClient(post_response={"run_id": "RUN-1"})
    execution = _execution_with_parent(client, online=False)
    execution.project_protocol_script_dir = tmp_path / "protocol.json"

    assert execution.execute() is False
    assert client.posts == []


def test_execute_returns_false_without_api(tmp_path) -> None:
    execution = OrchestratorExecution.__new__(OrchestratorExecution)
    execution.parent_ref = SimpleNamespace(
        status_widget=SimpleNamespace(text=lambda: "Online"),
        api_process=None,
    )
    execution.active_run_id = None
    execution.project_protocol_script_dir = tmp_path / "protocol.json"

    assert execution.execute() is False


def test_execute_returns_false_without_protocol_history() -> None:
    client = FakeClient(post_response={"run_id": "RUN-1"})
    execution = _execution_with_parent(client)
    execution.project_protocol_script_dir = None

    assert execution.execute() is False
    assert client.posts == []


def test_execute_starts_run_with_protocol_history_file_name(tmp_path) -> None:
    client = FakeClient(post_response={"run_id": "RUN-1"})
    execution = _execution_with_parent(client)
    execution.project_protocol_script_dir = tmp_path / "protocol.json"

    assert execution.execute() is True
    assert execution.active_run_id == "RUN-1"
    assert client.posts == [
        (
            "run/",
            {
                "snapshot": "protocol.json",
                "dry_run": False,
                "timeout_commands": "10 s",
            },
        ),
    ]


def test_stop_execution_returns_false_without_active_run() -> None:
    client = FakeClient(
        delete_response={"status": "cancelled"}, get_response={"run_id": None}
    )
    execution = _execution_with_parent(client)

    assert execution.stop_execution() is False
    assert client.gets == ["run/active"]
    assert client.deletes == []


def test_stop_execution_discovers_active_api_run() -> None:
    client = FakeClient(
        delete_response={"status": "cancelled"},
        get_response={"run_id": "RUN-1"},
    )
    execution = _execution_with_parent(client)
    execution._stop_run_polling = lambda: None

    assert execution.stop_execution() is True
    assert execution.active_run_id is None
    assert client.gets == ["run/active"]
    assert client.deletes == ["run/RUN-1"]


def test_stop_execution_cancels_active_run() -> None:
    client = FakeClient(delete_response={"status": "cancelled"})
    execution = _execution_with_parent(client)
    execution.active_run_id = "RUN-1"
    execution._stop_run_polling = lambda: None

    assert execution.stop_execution() is True
    assert execution.active_run_id is None
    assert client.deletes == ["run/RUN-1"]


def test_stop_execution_clears_state_when_run_is_already_gone() -> None:
    client = FakeClient(delete_response={"status_code": 404, "error": "not found"})
    execution = _execution_with_parent(client)
    execution.active_run_id = "RUN-1"
    execution._stop_run_polling = lambda: None

    assert execution.stop_execution() is True
    assert execution.active_run_id is None
    assert client.deletes == ["run/RUN-1"]


def test_incremental_text_avoids_duplicate_tail_lines() -> None:
    assert _incremental_text("alpha\n", "alpha\nbeta\n") == "beta\n"
    assert _incremental_text("alpha\nbeta\n", "beta\ngamma\n") == "gamma\n"
    assert _incremental_text("same", "same") == ""


def test_run_polling_thread_emits_status_pool_logs_and_finished(qtbot) -> None:
    class PollingClient:
        def get(self, endpoint: str, params=None, timeout: int = 10):
            if endpoint == "run/RUN-1/status":
                return {"run_id": "RUN-1", "state": "finished", "events": []}
            if endpoint == "run/pool":
                return [{"device": "pump"}]
            if endpoint == "logs/":
                return [
                    {
                        "filename": "run.log",
                        "modified": "2026-05-29T08:00:00",
                        "size_bytes": 14,
                    }
                ]
            if endpoint == "logs/run.log":
                return {"content": "line 1\nline 2\n"}
            return None

    thread = RunPollingThread(PollingClient(), "RUN-1", interval_ms=1)
    statuses = []
    pools = []
    logs = []
    thread.status_received.connect(statuses.append)  # type: ignore[attr-defined]
    thread.pool_drained.connect(pools.append)  # type: ignore[attr-defined]
    thread.logs_received.connect(logs.append)  # type: ignore[attr-defined]

    with qtbot.waitSignal(thread.run_finished, timeout=2000) as blocker:
        thread.start()
    thread.wait(1000)

    assert blocker.args == ["finished"]
    assert statuses == [{"run_id": "RUN-1", "state": "finished", "events": []}]
    assert pools == [[{"device": "pump"}]]
    assert logs == ["line 1\nline 2"]


def test_schema_validation_logs_unexpected_api_payload() -> None:
    records = []
    sink_id = logger.add(
        lambda message: records.append(message.record), level="WARNING"
    )

    try:
        parsed = _validate_model(
            RunStatus,
            {"state": "finished"},
            "GET run/RUN-1/status",
        )
    finally:
        logger.remove(sink_id)

    assert parsed is None
    assert len(records) == 1
    assert records[0]["extra"]["window"] == WindowCategory.EXECUTION
    assert "Unexpected API response for GET run/RUN-1/status" in records[0]["message"]
    assert "run_id" in records[0]["message"]
