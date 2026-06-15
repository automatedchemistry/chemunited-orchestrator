from __future__ import annotations

import json
from types import SimpleNamespace

from chemunited_workflow.api.schemas import RunRequest, RunStatus
from chemunited_workflow.enums import NodeState
from loguru import logger

from chemunited.orchestrator.execution import (
    OrchestratorExecution,
    RunEventStreamThread,
    RunPollingThread,
    StreamProcessStatusTracker,
    _incremental_text,
    _parse_sse_data_line,
    _process_name_from_protocol_key,
    _validate_model,
)
from chemunited.shared.enums import WindowCategory


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
    assert execution._active_process_order == [
        "clean_0",
        "ReactProcess_1",
        "my_process_2",
    ]
    assert execution._active_process_names == {
        "clean_0": "clean",
        "ReactProcess_1": "ReactProcess",
        "my_process_2": "my_process",
    }
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
    execution._run_execution_settings = RunRequest(timeout_commands="10 s")

    assert execution.execute() is True
    assert execution.active_run_id == "RUN-1"
    assert client.posts == [
        (
            "run/",
            {
                "snapshot": "protocol.json",
                "dry_run": False,
                "timeout_commands": "10 s",
                "error_resilient": False,
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
    assert client.gets == ["run/active", "run/RUN-1/report"]
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


def test_run_polling_thread_keeps_pool_and_logs_without_status_endpoint(qtbot) -> None:
    class PollingClient:
        def __init__(self) -> None:
            self.endpoints: list[str] = []

        def get(self, endpoint: str, params=None, timeout: int = 10):
            self.endpoints.append(endpoint)
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

    client = PollingClient()
    thread = RunPollingThread(client, "RUN-1", interval_ms=1)
    pools = []
    logs = []
    thread.pool_drained.connect(pools.append)  # type: ignore[attr-defined]
    thread.logs_received.connect(logs.append)  # type: ignore[attr-defined]

    try:
        thread.start()
        qtbot.waitUntil(lambda: bool(pools and logs), timeout=2000)
    finally:
        thread.stop()
        thread.wait(1000)

    assert "run/RUN-1/status" not in client.endpoints
    assert pools[0] == [{"device": "pump"}]
    assert logs == ["line 1\nline 2"]


def test_parse_sse_data_line_accepts_frames_and_ignores_bad_input() -> None:
    assert _parse_sse_data_line("") is None
    assert _parse_sse_data_line("event: ping") is None
    assert _parse_sse_data_line('data: {"state": "failed"}') == {"state": "failed"}
    assert _parse_sse_data_line(b'data: {"event_type": "EXECUTION_STARTED"}') == {
        "event_type": "EXECUTION_STARTED"
    }
    assert _parse_sse_data_line("data: {bad json}") is None


def test_stream_status_tracker_maps_order_and_terminal_states() -> None:
    tracker = StreamProcessStatusTracker(["Mixing_0", "SystemClean_1"])

    assert tracker.apply({"event_type": "EXECUTION_STARTED"}) == (
        [("Mixing_0", NodeState.RUNNING)],
        None,
    )
    assert tracker.apply({"event_type": "EXECUTION_FINISHED"}) == (
        [("Mixing_0", NodeState.COMPLETED)],
        None,
    )
    assert tracker.apply({"event_type": "EXECUTION_STARTED"}) == (
        [("SystemClean_1", NodeState.RUNNING)],
        None,
    )
    assert tracker.apply({"state": "FAILED", "node_key": "script_1"}) == (
        [("SystemClean_1", NodeState.FAILED)],
        None,
    )
    assert tracker.apply({"event_type": "EXECUTION_FINISHED"}) == (
        [("SystemClean_1", NodeState.FAILED)],
        None,
    )
    assert tracker.apply({"state": "failed"}) == (
        [("SystemClean_1", NodeState.FAILED)],
        "failed",
    )


def test_stream_status_tracker_maps_cancelled_running_process_to_inactive() -> None:
    tracker = StreamProcessStatusTracker(["Mixing_0"])

    tracker.apply({"event_type": "EXECUTION_STARTED"})

    assert tracker.apply({"state": "cancelled"}) == (
        [("Mixing_0", NodeState.INACTIVE)],
        "cancelled",
    )


def test_stream_status_tracker_prefers_payload_process_key() -> None:
    tracker = StreamProcessStatusTracker(["Mixing_0", "SystemClean_1"])

    assert tracker.apply(
        {"event_type": "EXECUTION_STARTED", "process": "SystemClean_1"}
    ) == (
        [("SystemClean_1", NodeState.RUNNING)],
        None,
    )
    assert tracker.current_process_name == "SystemClean_1"
    assert tracker.apply(
        {"event_type": "NODE_FAILED", "process": "SystemClean_1", "state": "FAILED"}
    ) == (
        [("SystemClean_1", NodeState.FAILED)],
        None,
    )


def test_run_event_stream_thread_emits_statuses_from_sse(qtbot) -> None:
    class Response:
        def __init__(self, lines) -> None:
            self.lines = lines
            self.closed = False

        def iter_lines(self, chunk_size: int = 512, decode_unicode: bool = False):
            assert chunk_size == 1
            yield from self.lines

        def close(self) -> None:
            self.closed = True

    class StreamClient:
        def __init__(self) -> None:
            self.response = Response(
                [
                    'data: {"event_type": "EXECUTION_STARTED"}',
                    "",
                    'data: {"event_type": "EXECUTION_FINISHED"}',
                    'data: {"event_type": "EXECUTION_STARTED"}',
                    'data: {"event_type": "NODE_RUNNING", "process": "SystemClean_1", "node_key": ["script_1", 0], "state": "RUNNING"}',
                    'data: {"event_type": "NODE_FAILED", "process": "SystemClean_1", "node_key": ["script_1", 0], "state": "FAILED"}',
                    'data: {"event_type": "EXECUTION_FINISHED"}',
                    'data: {"state": "failed"}',
                ]
            )
            self.streams: list[str] = []

        def stream(self, endpoint: str, timeout=10):
            self.streams.append(endpoint)
            return self.response

    client = StreamClient()
    stream_events = []
    statuses = []
    node_statuses = []
    thread = RunEventStreamThread(
        client,
        "RUN-1",
        ["Mixing_0", "SystemClean_1"],
    )
    thread.stream_event_received.connect(  # type: ignore[attr-defined]
        lambda run_id, payload: stream_events.append((run_id, payload))
    )
    thread.process_status_received.connect(  # type: ignore[attr-defined]
        lambda active_name, status: statuses.append((active_name, status))
    )
    thread.node_status_received.connect(  # type: ignore[attr-defined]
        lambda active_name, node_key, status: node_statuses.append(
            (active_name, node_key, status)
        )
    )

    with qtbot.waitSignal(thread.run_finished, timeout=2000) as blocker:
        thread.start()
    thread.wait(1000)

    assert blocker.args == ["failed"]
    assert client.streams == ["run/RUN-1/stream"]
    assert stream_events == [
        ("RUN-1", {"event_type": "EXECUTION_STARTED"}),
        ("RUN-1", {"event_type": "EXECUTION_FINISHED"}),
        ("RUN-1", {"event_type": "EXECUTION_STARTED"}),
        (
            "RUN-1",
            {
                "event_type": "NODE_RUNNING",
                "process": "SystemClean_1",
                "node_key": ["script_1", 0],
                "state": "RUNNING",
            },
        ),
        (
            "RUN-1",
            {
                "event_type": "NODE_FAILED",
                "process": "SystemClean_1",
                "node_key": ["script_1", 0],
                "state": "FAILED",
            },
        ),
        ("RUN-1", {"event_type": "EXECUTION_FINISHED"}),
        ("RUN-1", {"state": "failed"}),
    ]
    assert statuses == [
        ("Mixing_0", NodeState.RUNNING),
        ("Mixing_0", NodeState.COMPLETED),
        ("SystemClean_1", NodeState.RUNNING),
        ("SystemClean_1", NodeState.FAILED),
        ("SystemClean_1", NodeState.FAILED),
        ("SystemClean_1", NodeState.FAILED),
    ]
    assert node_statuses == [
        ("SystemClean_1", "script_1", NodeState.RUNNING),
        ("SystemClean_1", "script_1", NodeState.FAILED),
    ]


def test_run_event_stream_thread_ignores_invalid_node_status_frames(qtbot) -> None:
    class Response:
        def iter_lines(self, chunk_size: int = 512, decode_unicode: bool = False):
            assert chunk_size == 1
            yield 'data: {"event_type": "EXECUTION_STARTED"}'
            yield 'data: {"event_type": "NODE_RUNNING", "state": "RUNNING"}'
            yield 'data: {"event_type": "NODE_RUNNING", "node_key": "script_1", "state": "UNKNOWN"}'
            yield 'data: {"event_type": "NODE_RUNNING", "node_key": ["script_2", 0], "state": "WAITING"}'
            yield 'data: {"state": "finished"}'

        def close(self) -> None:
            pass

    class StreamClient:
        def stream(self, endpoint: str, timeout=10):
            return Response()

    node_statuses = []
    thread = RunEventStreamThread(StreamClient(), "RUN-1", ["Mixing_0"])
    thread.node_status_received.connect(  # type: ignore[attr-defined]
        lambda active_name, node_key, status: node_statuses.append(
            (active_name, node_key, status)
        )
    )

    with qtbot.waitSignal(thread.run_finished, timeout=2000):
        thread.start()
    thread.wait(1000)

    assert node_statuses == [("Mixing_0", "script_2", NodeState.WAITING)]


def test_finish_run_fetches_emits_and_applies_report_once() -> None:
    report = {
        "run_id": "RUN-1",
        "state": "finished",
        "results": [{"node_state": {"start:0": "COMPLETED"}}],
    }
    client = FakeClient(get_response=report)
    execution = OrchestratorExecution.__new__(OrchestratorExecution)
    execution.parent_ref = SimpleNamespace(api_process=SimpleNamespace(client=client))
    execution.active_run_id = "RUN-1"
    execution._stop_run_polling = lambda: None
    finished = []
    emitted_reports = []
    applied_reports = []
    execution._emit_signal = lambda name, value: finished.append((name, value))
    execution._emit_run_report = lambda run_id, payload: emitted_reports.append(
        (run_id, payload)
    )
    execution._apply_run_report = lambda run_id, payload: applied_reports.append(
        (run_id, payload)
    )

    execution._finish_run("finished")

    assert execution.active_run_id is None
    assert client.gets == ["run/RUN-1/report"]
    assert emitted_reports == [("RUN-1", report)]
    assert applied_reports == [("RUN-1", report)]
    assert finished == [("protocol_execution_finished", "finished")]


def test_orchestrator_execution_updates_workflow_node_status_by_active_key() -> None:
    class Workflow:
        def __init__(self) -> None:
            self.cleared = False

        def clear_progress(self) -> None:
            self.cleared = True

    class WorkflowsWidget:
        def __init__(self) -> None:
            self.workflow = Workflow()
            self.selected: list[str] = []
            self.updates: list[tuple[str, str, NodeState]] = []

        def __getitem__(self, process_name: str):
            if process_name == "Mixing":
                return self.workflow
            return None

        def set_node_status(
            self,
            process_name: str,
            node_name: str,
            status: NodeState,
        ) -> None:
            self.updates.append((process_name, node_name, status))

        def select_process(self, process_name: str) -> None:
            self.selected.append(process_name)

    workflows_widget = WorkflowsWidget()
    execution = OrchestratorExecution.__new__(OrchestratorExecution)
    execution.parent_ref = SimpleNamespace(workflows_protocol=workflows_widget)
    execution._active_process_names = {"Mixing_0": "Mixing"}

    execution._on_process_status_received("Mixing_0", NodeState.RUNNING)
    execution._on_node_status_received("Mixing_0", "script_1", NodeState.COMPLETED)

    assert workflows_widget.selected == ["Mixing"]
    assert workflows_widget.workflow.cleared is True
    assert workflows_widget.updates == [("Mixing", "script_1", NodeState.COMPLETED)]


def test_apply_run_report_prefers_report_process_key() -> None:
    emitted_nodes = []
    emitted_processes = []
    execution = OrchestratorExecution.__new__(OrchestratorExecution)
    execution._active_process_order = ["Wrong_0"]
    execution._emit_node_status = (
        lambda active_name, node_name, status: emitted_nodes.append(
            (active_name, node_name, status)
        )
    )
    execution._emit_process_status = (
        lambda active_name, status: emitted_processes.append((active_name, status))
    )

    execution._apply_run_report(
        "RUN-1",
        {
            "results": [
                {
                    "process": "Mixing_0",
                    "node_state": {
                        "start:0": "COMPLETED",
                        "script_1:0": "FAILED",
                    },
                }
            ]
        },
    )

    assert emitted_nodes == [
        ("Mixing_0", "start:0", NodeState.COMPLETED),
        ("Mixing_0", "script_1:0", NodeState.FAILED),
    ]
    assert emitted_processes == [("Mixing_0", NodeState.FAILED)]


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
