import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from chemunited_workflow.api.schemas import LogMeta, RunRequest, RunStatus
from loguru import logger as _logger
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError
from PyQt5.QtCore import QThread, pyqtSignal

from chemunited.qt.monitoring.execution_api_process import ApiClient
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
        finish_state = "stopped"
        while not self._stop_requested:
            try:
                status_payload = self.client.get(
                    f"run/{quote(self.run_id)}/status",
                    timeout=5,
                )
                status = _validate_model(
                    RunStatus,
                    status_payload,
                    f"GET run/{self.run_id}/status",
                )
                if status is not None:
                    logger.info(
                        "Run {} status={} events={}",
                        status.run_id,
                        status.state,
                        len(status.events),
                    )
                    self.status_received.emit(status.model_dump())
                    if _is_terminal_run_status(status):
                        finish_state = _run_state(status)
                        self._poll_pool()
                        self._poll_logs()
                        self.run_finished.emit(finish_state)
                        return

                self._poll_pool()
                self._poll_logs()
            except Exception as exc:
                logger.warning("Run polling failed for {}: {}", self.run_id, exc)

            self.msleep(self.interval_ms)

        self.run_finished.emit(finish_state)

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

    def __init__(self, parent):
        super().__init__(parent)
        self.project_protocol_script_dir: Path | None = None
        self.active_run_id: str | None = None
        self._run_polling_thread: RunPollingThread | None = None

    def set_project_protocol_script_dir(self, dir: Path) -> None:
        self.project_protocol_script_dir = dir
        with open(self.project_protocol_script_dir, "r", encoding="utf-8") as f:
            data = json.load(f)

        actual_process: str = ""
        for key in data:
            if key == "main_parameter":
                continue
            process_name = _process_name_from_protocol_key(key)
            if process_name is None:
                continue
            if hasattr(self.parent_ref.protocols_widget, "activate_process"):
                self.parent_ref.protocols_widget.activate_process(process_name)
                if not actual_process:
                    actual_process = process_name
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
        request = RunRequest(snapshot=snapshot_name, dry_run=False)
        response = api_process.client.post(
            "run/",
            data=request.model_dump(),
        )
        started = _validate_model(RunStartedResponse, response, "POST run/")
        if started is None:
            logger.error("Failed to start protocol execution: {}", response)
            return False

        run_id = started.run_id
        self.active_run_id = run_id
        logger.info("Protocol execution started with run_id={}", run_id)
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
        thread = RunPollingThread(client, run_id, parent=self)
        thread.logs_received.connect(self._append_execution_log_text)  # type: ignore[attr-defined]
        thread.run_finished.connect(self._on_run_polling_finished)  # type: ignore[attr-defined]
        self._run_polling_thread = thread
        thread.start()

    def _stop_run_polling(self) -> None:
        thread = getattr(self, "_run_polling_thread", None)
        if thread is None:
            return
        thread.stop()
        if thread.isRunning():
            thread.wait(1500)
        self._run_polling_thread = None

    def _on_run_polling_finished(self, state: str) -> None:
        if self.active_run_id is None:
            return
        self._finish_run(state)

    def _finish_run(self, state: str) -> None:
        self.active_run_id = None
        self._stop_run_polling()
        logger.info("Protocol execution finished with state={}", state)
        self._emit_signal("protocol_execution_finished", state)

    def _append_execution_log_text(self, text: str) -> None:
        frame = getattr(self.parent_ref, "FrameLoggings", None)
        browser = getattr(frame, "detail_loggins", None)
        if browser is not None and text.strip():
            browser.append(text.rstrip())

    def _emit_signal(self, name: str, value: str) -> None:
        try:
            signal = getattr(self, name, None)
            emit = getattr(signal, "emit", None)
            if emit is not None:
                emit(value)
        except RuntimeError:
            pass
