import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from chemunited_workflow.api.schemas import LogMeta, RunStatus
from chemunited_workflow.enums import NodeState
from loguru import logger as _logger
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError
from PyQt5.QtCore import QThread, pyqtSignal

from chemunited.qt.monitoring.execution_api_process import ApiClient, RunRequestDialog
from chemunited.qt.shared.enums import WindowCategory

from .connectivity import OrchestratorConnectivity

logger = _logger.bind(window=WindowCategory.EXECUTION)

TERMINAL_RUN_STATES = {
    "completed",
    "failed",
    "cancelled",
    "canceled",
    "stopped",
    "finished",
    "error",
}


class RunStartedResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str


class ActiveRunResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    run_id: str | None


class LogContentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str


LOG_LIST_RESPONSE = TypeAdapter(list[LogMeta])
POOL_RESPONSE = TypeAdapter(list[dict[str, Any]])
STOPPED_RUN_STATES = {"cancelled", "canceled", "stopped"}


def _process_name_from_protocol_key(key: str) -> str | None:
    process_name, separator, process_index = key.rpartition("_")
    if not separator or not process_name or not process_index.isdecimal():
        return None
    return process_name


def _validate_model(model: type[BaseModel], payload: Any, endpoint: str):
    if payload is None:
        return None
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "Unexpected API response for {}: {}. Payload: {}",
            endpoint,
            _validation_error_summary(exc),
            payload,
        )
        return None


def _validate_adapter(adapter: TypeAdapter, payload: Any, endpoint: str):
    if payload is None:
        return None
    try:
        return adapter.validate_python(payload)
    except ValidationError as exc:
        logger.warning(
            "Unexpected API response for {}: {}. Payload: {}",
            endpoint,
            _validation_error_summary(exc),
            payload,
        )
        return None


def _validation_error_summary(exc: ValidationError) -> str:
    parts = []
    for error in exc.errors()[:3]:
        location = ".".join(str(part) for part in error.get("loc", ())) or "<root>"
        parts.append(f"{location}: {error.get('msg', 'invalid value')}")
    if len(exc.errors()) > 3:
        parts.append(f"{len(exc.errors()) - 3} more error(s)")
    return "; ".join(parts)


def _run_state(status: RunStatus) -> str:
    return status.state.strip().lower()


def _is_terminal_run_status(status: RunStatus) -> bool:
    return _run_state(status) in TERMINAL_RUN_STATES


def _latest_log_filename(logs: list[LogMeta]) -> str | None:
    if not logs:
        return None
    return Path(logs[0].filename).name


def _log_text(payload: Any) -> str | None:
    content = _validate_model(LogContentResponse, payload, "GET logs/{filename}")
    if content is not None:
        return content.content
    return None


def _incremental_text(previous: str, current: str) -> str:
    if not current or current == previous:
        return ""
    if current.startswith(previous):
        return current[len(previous) :]

    max_overlap = min(len(previous), len(current))
    for size in range(max_overlap, 0, -1):
        if previous[-size:] == current[:size]:
            return current[size:]
    return current


def _parse_sse_data_line(line: bytes | str) -> dict[str, Any] | None:
    if isinstance(line, bytes):
        line = line.decode(errors="replace")
    line = line.strip()
    if not line or not line.startswith("data:"):
        return None

    payload_text = line.removeprefix("data:").strip()
    if not payload_text:
        return None

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        logger.warning("Malformed run stream event ignored: {} ({})", payload_text, exc)
        return None

    if not isinstance(payload, dict):
        logger.warning("Run stream event is not an object: {}", payload)
        return None
    return payload


def _normalize_event_label(value: Any) -> str:
    if value is None:
        return ""
    value = getattr(value, "value", value)
    text = str(value).strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.upper()


def _stream_final_state(payload: dict[str, Any]) -> str | None:
    if "event_type" in payload:
        return None
    if set(payload) != {"state"}:
        return None
    state = payload.get("state")
    if state is None:
        return None
    text = str(getattr(state, "value", state)).strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.lower()


def _node_state_from_stream_payload(payload: dict[str, Any]) -> NodeState | None:
    if _node_name_from_stream_payload(payload) is None or "state" not in payload:
        return None
    state = _normalize_event_label(payload.get("state"))
    if not state:
        return None
    try:
        return NodeState(state)
    except ValueError:
        try:
            return NodeState[state]
        except KeyError:
            logger.debug("Ignoring stream node state that is not NodeState: {}", state)
            return None


def _node_name_from_stream_payload(payload: dict[str, Any]) -> str | None:
    node_key = payload.get("node_key")
    if isinstance(node_key, (list, tuple)):
        if not node_key:
            return None
        node_key = node_key[0]
    if node_key is None:
        return None
    node_name = str(node_key).strip()
    return node_name or None


class StreamProcessStatusTracker:
    """Infers active process status from stream events and protocol order."""

    def __init__(self, active_process_order: list[str]) -> None:
        self.active_process_order = list(active_process_order)
        self._current_index = -1
        self._current_failed = False

    def apply(
        self,
        payload: dict[str, Any],
    ) -> tuple[list[tuple[str, NodeState]], str | None]:
        final_state = _stream_final_state(payload)
        if final_state is not None:
            return self._apply_final_state(final_state), final_state

        event_type = _normalize_event_label(payload.get("event_type"))
        state = _normalize_event_label(payload.get("state"))
        updates: list[tuple[str, NodeState]] = []

        if event_type == "EXECUTION_STARTED":
            active_name = self._advance_to_next_process()
            if active_name is not None:
                updates.append((active_name, NodeState.RUNNING))
            return updates, None

        active_name = self.current_process_name
        if active_name is None:
            return updates, None

        if state == "FAILED" or event_type == "NODE_FAILED":
            self._current_failed = True
            updates.append((active_name, NodeState.FAILED))

        if event_type == "EXECUTION_FINISHED":
            updates.append(
                (
                    active_name,
                    NodeState.FAILED if self._current_failed else NodeState.COMPLETED,
                )
            )

        return updates, None

    @property
    def current_process_name(self) -> str | None:
        if 0 <= self._current_index < len(self.active_process_order):
            return self.active_process_order[self._current_index]
        return None

    def _advance_to_next_process(self) -> str | None:
        next_index = self._current_index + 1
        if next_index >= len(self.active_process_order):
            logger.warning(
                "Run stream reported more process starts than protocol entries: {}",
                self.active_process_order,
            )
            return None
        self._current_index = next_index
        self._current_failed = False
        return self.current_process_name

    def _apply_final_state(self, state: str) -> list[tuple[str, NodeState]]:
        active_name = self.current_process_name
        if active_name is None:
            return []
        if state in {"failed", "error"}:
            self._current_failed = True
            return [(active_name, NodeState.FAILED)]
        if state in STOPPED_RUN_STATES:
            return [(active_name, NodeState.INACTIVE)]
        if self._current_failed:
            return [(active_name, NodeState.FAILED)]
        return [(active_name, NodeState.COMPLETED)]


class RunEventStreamThread(QThread):
    stream_event_received = pyqtSignal(str, object)
    process_status_received = pyqtSignal(str, object)
    node_status_received = pyqtSignal(str, str, object)
    run_finished = pyqtSignal(str)

    def __init__(
        self,
        client: ApiClient,
        run_id: str,
        active_process_order: list[str],
        *,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.run_id = run_id
        self._tracker = StreamProcessStatusTracker(active_process_order)
        self._stop_requested = False
        self._response = None

    def stop(self) -> None:
        self._stop_requested = True
        response = self._response
        close = getattr(response, "close", None)
        if close is not None:
            close()

    def run(self) -> None:
        try:
            self._response = self.client.stream(
                f"run/{quote(self.run_id)}/stream",
                timeout=(5, 15),
            )
            for line in self._response.iter_lines(
                chunk_size=1,
                decode_unicode=True,
            ):
                if self._stop_requested:
                    return
                payload = _parse_sse_data_line(line)
                if payload is None:
                    continue
                self.stream_event_received.emit(self.run_id, payload)
                updates, final_state = self._tracker.apply(payload)
                for active_name, status in updates:
                    self.process_status_received.emit(active_name, status)
                node_state = _node_state_from_stream_payload(payload)
                active_name = self._tracker.current_process_name
                node_name = _node_name_from_stream_payload(payload)
                if node_state is not None and active_name is not None and node_name:
                    self.node_status_received.emit(
                        active_name,
                        node_name,
                        node_state,
                    )
                if final_state is not None:
                    self.run_finished.emit(final_state)
                    return
        except Exception as exc:
            if not self._stop_requested:
                logger.warning("Run stream failed for {}: {}", self.run_id, exc)
                self.run_finished.emit("error")
        finally:
            self._response = None


class RunPollingThread(QThread):
    status_received = pyqtSignal(object)
    pool_drained = pyqtSignal(object)
    logs_received = pyqtSignal(str)
    run_finished = pyqtSignal(str)

    def __init__(
        self,
        client: ApiClient,
        run_id: str,
        *,
        interval_ms: int = 1000,
        log_tail: int = 200,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.client = client
        self.run_id = run_id
        self.interval_ms = interval_ms
        self.log_tail = log_tail
        self._stop_requested = False
        self._last_log_filename: str | None = None
        self._last_log_text = ""

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        while not self._stop_requested:
            try:
                self._poll_pool()
                self._poll_logs()
            except Exception as exc:
                logger.warning(
                    "Run auxiliary polling failed for {}: {}", self.run_id, exc
                )

            self.msleep(self.interval_ms)

    def _poll_pool(self) -> None:
        pool_payload = self.client.get("run/pool", timeout=5)
        pool = _validate_adapter(POOL_RESPONSE, pool_payload, "GET run/pool")
        if not pool:
            return
        logger.info("Run pool drained: {} command(s)", len(pool))
        self.pool_drained.emit(pool)

    def _poll_logs(self) -> None:
        logs_payload = self.client.get("logs/", timeout=5)
        logs = _validate_adapter(LOG_LIST_RESPONSE, logs_payload, "GET logs/")
        if logs is None:
            return
        filename = _latest_log_filename(logs)
        if not filename:
            return

        if filename != self._last_log_filename:
            self._last_log_filename = filename
            self._last_log_text = ""

        log_payload = self.client.get(
            f"logs/{quote(filename)}",
            params={"tail": self.log_tail},
            timeout=5,
        )
        text = _log_text(log_payload)
        if text is None:
            return
        new_text = _incremental_text(self._last_log_text, text).strip("\n")
        self._last_log_text = text
        if new_text:
            self.logs_received.emit(new_text)


class OrchestratorExecution(OrchestratorConnectivity):
    protocol_execution_started = pyqtSignal(str)
    protocol_execution_finished = pyqtSignal(str)
    process_status_changed = pyqtSignal(str, object)
    node_status_changed = pyqtSignal(str, str, object)
    run_stream_event_received = pyqtSignal(str, object)
    run_report_received = pyqtSignal(str, object)

    def __init__(self, parent):
        super().__init__(parent)
        self.project_protocol_script_dir: Path | None = None
        self.active_run_id: str | None = None
        self._run_polling_thread: RunPollingThread | None = None
        self._run_stream_thread: RunEventStreamThread | None = None
        self._active_process_order: list[str] = []
        self._active_process_names: dict[str, str] = {}

    def set_project_protocol_script_dir(self, dir: Path) -> None:
        self.project_protocol_script_dir = dir
        with open(self.project_protocol_script_dir, "r", encoding="utf-8") as f:
            data = json.load(f)

        active_processes: list[tuple[str, str]] = []
        actual_process: str = ""
        for key in data:
            if key == "main_parameter":
                continue
            process_name = _process_name_from_protocol_key(key)
            if process_name is None:
                continue
            active_processes.append((key, process_name))
            if not actual_process:
                actual_process = process_name

        self._active_process_order = [
            active_name for active_name, _ in active_processes
        ]
        self._active_process_names = dict(active_processes)

        protocols_widget = getattr(self.parent_ref, "protocols_widget", None)
        if protocols_widget is not None:
            if hasattr(protocols_widget, "set_active_processes"):
                protocols_widget.set_active_processes(active_processes)
            elif hasattr(protocols_widget, "activate_process"):
                for active_name, process_name in active_processes:
                    try:
                        protocols_widget.activate_process(active_name, process_name)
                    except TypeError:
                        protocols_widget.activate_process(process_name)

        self._reset_process_statuses()
        if actual_process:
            self.select_process(actual_process)

    def execute(self) -> bool:
        """
        Start execution of the selected protocol through the workflow run API.
        Return True only when a run is started successfully.
        """
        if self.parent_ref.status_widget.text() == "Offline":
            logger.warning("No API running - connect first.")
            return False
        api_process = self.parent_ref.api_process
        if api_process is None:
            logger.warning("No API running - connect first.")
            return False
        if getattr(self, "active_run_id", None) is not None:
            logger.warning("Protocol execution is already running.")
            return False
        if self.project_protocol_script_dir is None:
            logger.error("No protocol history file selected.")
            return False

        snapshot_name = self.project_protocol_script_dir.name
        dialog = RunRequestDialog(snapshot=snapshot_name, parent=self.parent_ref)
        if dialog.exec() != dialog.Accepted:
            return False
        run_request = dialog.get_result_instance()
        if run_request is None:
            return False
        response = api_process.client.post(
            "run/",
            data=run_request.model_dump(),
        )
        started = _validate_model(RunStartedResponse, response, "POST run/")
        if started is None:
            logger.error("Failed to start protocol execution: {}", response)
            return False

        run_id = started.run_id
        self.active_run_id = run_id
        logger.info("Protocol execution started with run_id={}", run_id)
        self._reset_process_statuses()
        self._emit_signal("protocol_execution_started", run_id)
        self._start_run_polling(api_process.client, run_id)
        return True

    def stop_execution(self) -> bool:
        """Cancel the active workflow run through DELETE /run/{run_id}."""
        api_process = self.parent_ref.api_process
        if api_process is None:
            logger.warning("No API running - cannot stop protocol execution.")
            return False

        run_id = getattr(self, "active_run_id", None)
        if run_id is None:
            active_payload = api_process.client.get("run/active")
            active = _validate_model(
                ActiveRunResponse,
                active_payload,
                "GET run/active",
            )
            if active is None:
                logger.warning("Could not read active run from API.")
                return False
            run_id = active.run_id
            if run_id is None:
                logger.warning("There is nothing running to be stopped.")
                return False
            self.active_run_id = run_id

        response = api_process.client.delete(f"run/{quote(run_id)}")
        if response is None:
            logger.error("Failed to cancel protocol execution run_id={}", run_id)
            return False
        if isinstance(response, dict) and response.get("status_code") == 404:
            logger.info("Protocol execution run_id={} was already gone.", run_id)
            self._finish_run("cancelled")
            return True

        logger.info("Protocol execution cancellation requested for run_id={}", run_id)
        self._finish_run("cancelled")
        return True

    def _start_run_polling(self, client: ApiClient, run_id: str) -> None:
        self._stop_run_polling()
        stream_thread = RunEventStreamThread(
            client,
            run_id,
            list(getattr(self, "_active_process_order", [])),
            parent=self,
        )
        stream_thread.stream_event_received.connect(  # type: ignore[attr-defined]
            self._emit_run_stream_event
        )
        stream_thread.process_status_received.connect(  # type: ignore[attr-defined]
            self._on_process_status_received
        )
        stream_thread.node_status_received.connect(  # type: ignore[attr-defined]
            self._on_node_status_received
        )
        stream_thread.run_finished.connect(self._on_run_polling_finished)  # type: ignore[attr-defined]
        self._run_stream_thread = stream_thread

        polling_thread = RunPollingThread(client, run_id, parent=self)
        polling_thread.logs_received.connect(self._append_execution_log_text)  # type: ignore[attr-defined]
        self._run_polling_thread = polling_thread

        stream_thread.start()
        polling_thread.start()

    def _stop_run_polling(self) -> None:
        for attr_name in ("_run_stream_thread", "_run_polling_thread"):
            thread = getattr(self, attr_name, None)
            if thread is None:
                continue
            thread.stop()
            if thread.isRunning():
                thread.wait(1500)
            setattr(self, attr_name, None)

    def _on_process_status_received(self, active_name: str, status: NodeState) -> None:
        if status == NodeState.RUNNING:
            self._select_workflow_process(active_name)
            self._reset_workflow_process_status(active_name)
        elif status in {NodeState.COMPLETED, NodeState.FAILED, NodeState.INACTIVE}:
            self._finalize_workflow_process_nodes(active_name, status)
        self._emit_process_status(active_name, status)

    def _on_node_status_received(
        self,
        active_name: str,
        node_name: str,
        status: NodeState,
    ) -> None:
        self._emit_node_status(active_name, node_name, status)

    def _on_run_polling_finished(self, state: str) -> None:
        if self.active_run_id is None:
            return
        self._finish_run(state)

    def _finish_run(self, state: str) -> None:
        run_id = self.active_run_id
        self.active_run_id = None
        self._stop_run_polling()
        logger.info("Protocol execution finished with state={}", state)
        if run_id is not None:
            report = self._fetch_run_report(run_id)
            self._emit_run_report(run_id, report)
            if report is not None:
                self._apply_run_report(run_id, report)
        self._emit_signal("protocol_execution_finished", state)

    def _fetch_run_report(self, run_id: str) -> dict[str, Any] | None:
        api_process = getattr(self.parent_ref, "api_process", None)
        if api_process is None:
            return None
        payload = api_process.client.get(f"run/{quote(run_id)}/report", timeout=10)
        if not isinstance(payload, dict):
            return None
        return payload

    def _apply_run_report(self, run_id: str, payload: dict[str, Any]) -> None:
        results = payload.get("results")
        if not isinstance(results, list):
            return
        logger.info(
            "Applying run report for run_id={}: {} process result(s)",
            run_id,
            len(results),
        )
        for i, result in enumerate(results):
            if i >= len(self._active_process_order):
                break
            active_name = self._active_process_order[i]
            node_states: dict[str, str] = result.get("node_state", {})
            for node_name, state_str in node_states.items():
                try:
                    node_state = NodeState(state_str)
                except ValueError:
                    try:
                        node_state = NodeState[state_str]
                    except KeyError:
                        logger.debug(
                            "Unknown node state in report for {}: {}", node_name, state_str
                        )
                        continue
                self._emit_node_status(active_name, node_name, node_state)
            states = list(node_states.values())
            process_status = (
                NodeState.FAILED if any(s == "FAILED" for s in states) else NodeState.COMPLETED
            )
            self._emit_process_status(active_name, process_status)

    def _append_execution_log_text(self, text: str) -> None:
        frame = getattr(self.parent_ref, "FrameLoggings", None)
        browser = getattr(frame, "detail_loggins", None)
        if browser is not None and text.strip():
            browser.append(text.rstrip())

    def _reset_process_statuses(self) -> None:
        self._reset_workflow_node_statuses()
        try:
            active_process_order = object.__getattribute__(
                self,
                "_active_process_order",
            )
        except (AttributeError, RuntimeError):
            active_process_order = []
        for active_name in active_process_order:
            self._emit_process_status(active_name, NodeState.NOT_VISITED)

    def _emit_process_status(self, active_name: str, status: NodeState) -> None:
        try:
            self.process_status_changed.emit(active_name, status)  # type: ignore[attr-defined]
        except RuntimeError:
            pass

    def _emit_node_status(
        self,
        active_name: str,
        node_name: str,
        status: NodeState,
    ) -> None:
        try:
            self.node_status_changed.emit(active_name, node_name, status)  # type: ignore[attr-defined]
        except RuntimeError:
            pass
        self._update_workflow_node_status(active_name, node_name, status)

    def _emit_run_stream_event(self, run_id: str, payload: dict[str, Any]) -> None:
        try:
            self.run_stream_event_received.emit(run_id, payload)  # type: ignore[attr-defined]
        except RuntimeError:
            pass

    def _emit_run_report(self, run_id: str, payload: dict[str, Any] | None) -> None:
        try:
            self.run_report_received.emit(run_id, payload)  # type: ignore[attr-defined]
        except RuntimeError:
            pass

    def _reset_workflow_node_statuses(self) -> None:
        workflows_widget = getattr(self.parent_ref, "workflows_protocol", None)
        clear_progress = getattr(workflows_widget, "clear_progress", None)
        if callable(clear_progress):
            clear_progress()

    def _reset_workflow_process_status(self, active_name: str) -> None:
        process_name = self._process_name_for_active_key(active_name)
        workflows_widget = getattr(self.parent_ref, "workflows_protocol", None)
        if process_name is None or workflows_widget is None:
            return
        workflow = None
        getitem = getattr(workflows_widget, "__getitem__", None)
        if callable(getitem):
            workflow = getitem(process_name)
        if workflow is not None and hasattr(workflow, "clear_progress"):
            workflow.clear_progress()

    def _finalize_workflow_process_nodes(self, active_name: str, status: NodeState) -> None:
        process_name = self._process_name_for_active_key(active_name)
        workflows_widget = getattr(self.parent_ref, "workflows_protocol", None)
        if process_name is None or workflows_widget is None:
            return
        finalize = getattr(workflows_widget, "finalize_running_nodes", None)
        if callable(finalize):
            finalize(process_name, status)

    def _select_workflow_process(self, active_name: str) -> None:
        process_name = self._process_name_for_active_key(active_name)
        workflows_widget = getattr(self.parent_ref, "workflows_protocol", None)
        if process_name is None or workflows_widget is None:
            return
        select_process = getattr(workflows_widget, "select_process", None)
        if callable(select_process):
            select_process(process_name)
        recenter_view = getattr(workflows_widget, "recenter_view", None)
        if callable(recenter_view):
            recenter_view()

    def _update_workflow_node_status(
        self,
        active_name: str,
        node_name: str,
        status: NodeState,
    ) -> None:
        process_name = self._process_name_for_active_key(active_name)
        workflows_widget = getattr(self.parent_ref, "workflows_protocol", None)
        if process_name is None or workflows_widget is None:
            return
        set_node_status = getattr(workflows_widget, "set_node_status", None)
        if callable(set_node_status):
            set_node_status(process_name, node_name, status)

    def _process_name_for_active_key(self, active_name: str) -> str | None:
        active_process_names = getattr(self, "_active_process_names", {})
        process_name = active_process_names.get(active_name)
        if process_name is not None:
            return process_name
        return _process_name_from_protocol_key(active_name)

    def _emit_signal(self, name: str, value: str) -> None:
        try:
            signal = getattr(self, name, None)
            emit = getattr(signal, "emit", None)
            if emit is not None:
                emit(value)
        except RuntimeError:
            pass
