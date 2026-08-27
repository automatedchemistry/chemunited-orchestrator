"""RunnerService — parses protocols and drives workflow execution."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from loguru import logger
from pydantic import BaseModel

from chemunited_workflow import Process, WorkflowExecutor, compile_workflow
from chemunited_workflow.cancellation import wait_for_operator_input, wait_while_paused
from chemunited_workflow.durations import parse_timeout_commands
from chemunited_workflow.platform import Platform
from chemunited_workflow.terminal import WorkflowLogger, create_run_log_path

from ..run_store import RunState, RunStore
from .monitoring import MonitoringService


class RunnerService:
    def __init__(
        self,
        project_dir: Path,
        processes: dict[str, type[Process]],
        configs: dict[str, type[BaseModel]],
        run_store: RunStore,
        monitoring_service: MonitoringService | None = None,
    ) -> None:
        self._project_dir = project_dir
        self._processes = processes
        self._configs = configs
        self._run_store = run_store
        self._monitoring_service = monitoring_service

    def start(
        self,
        protocol_filename: str,
        *,
        dry_run: bool = False,
        timeout_commands: str = "10 s",
        error_resilient: bool = False,
        record_monitoring: bool = False,
    ) -> str | None:
        """Launch execution in a background thread. Returns run_id, or None if busy.

        Parameters
        ----------
        dry_run:
            When ``True``, all HTTP calls to devices are suppressed. The workflow
            graph, node logic, and concurrency guard run normally.
        timeout_commands:
            Feedback polling timeout, such as ``"10 s"``. Empty string disables
            the timeout.
        record_monitoring:
            When ``True``, monitoring is forced on for the run's duration and
            every reading is persisted to ``log/monitoring/{run_id}/``, using
            whatever variables are currently registered in
            ``connectivity/monitoring.json``. Raises ``ValueError`` up front
            if no variables are registered — the run never starts, rather
            than starting and silently recording nothing.
        """
        parse_timeout_commands(timeout_commands)
        if record_monitoring:
            self._validate_record_monitoring()
        protocol_path = self._project_dir / "protocols_historic" / protocol_filename
        data = json.loads(protocol_path.read_text(encoding="utf-8"))
        sequence = self._parse_sequence(data)
        run_id = self._run_store.try_start(protocol_filename)
        if run_id is None:
            return None
        thread = threading.Thread(
            target=self._execute,
            args=(
                run_id,
                protocol_filename,
                sequence,
                data,
                dry_run,
                timeout_commands,
                error_resilient,
                record_monitoring,
            ),
            daemon=True,
        )
        thread.start()
        return run_id

    def _validate_record_monitoring(self) -> None:
        """Fail fast, before try_start() claims the run slot, if recording can't work.

        Checked at start() rather than inside on_run_started() so the caller
        gets a synchronous 422 and no run is created at all — as opposed to
        a run silently starting and recording nothing. A narrow race still
        exists if the monitoring config is emptied out after this check but
        before the background thread reaches on_run_started(); that path
        can't be turned into a hard error anymore (the run has already been
        accepted), so it falls back to on_run_started()'s own warn-and-skip.
        """
        if self._monitoring_service is None:
            raise ValueError(
                "record_monitoring was requested but monitoring is not "
                "available for this project."
            )
        if not self._monitoring_service.read_config().get("variables"):
            raise ValueError(
                "record_monitoring was requested but no monitoring variables "
                "are registered. PUT /monitoring/config first, or start the "
                "run without record_monitoring."
            )

    def _execute(
        self,
        run_id: str,
        protocol_filename: str,
        sequence: list[tuple[str, int]],
        data: dict,
        dry_run: bool,
        timeout_commands: str,
        error_resilient: bool,
        record_monitoring: bool,
    ) -> None:
        log_path = create_run_log_path(self._project_dir, protocol_filename)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        sink_id = logger.add(
            log_path,
            level="DEBUG",
            format="{time:YYYY-MM-DDTHH:mm:ss} | {level: <8} | {message}",
            colorize=False,
            encoding="utf-8",
        )
        try:
            pool_dir = self._project_dir / "log" / "pool"
            if pool_dir.exists():
                for f in pool_dir.glob("*.jsonl"):
                    f.unlink(missing_ok=True)
            cancellation_token = self._run_store.cancel_event()
            pause_event = self._run_store.pause_event()

            def request_input(
                node_id: str, message: str, timeout_seconds: float
            ) -> str:
                event = self._run_store.request_input(node_id, message)
                try:
                    wait_for_operator_input(event, cancellation_token, timeout_seconds)
                except Exception:
                    self._run_store.pop_input_value(node_id)
                    raise
                return self._run_store.pop_input_value(node_id) or ""

            platform = Platform.from_project_dir(
                self._project_dir,
                dry_run=dry_run,
                log_dir=self._project_dir / "log",
                timeout_commands=timeout_commands,
                error_resilient=error_resilient,
                cancellation_token=cancellation_token,
                pause_event=pause_event,
            )
            if self._monitoring_service is not None:
                self._monitoring_service.on_run_started(
                    run_id, record=record_monitoring
                )
            for process_name, process_index in sequence:
                # Honor a pause requested between processes, not just mid-node.
                wait_while_paused(pause_event, cancellation_token)
                record = self._run_store.get()
                if record is not None and record.state == RunState.CANCELLED:
                    return
                config_data = data.get(f"{process_name}_{process_index}", {})
                config = self._configs[process_name].model_validate(config_data)
                process = self._processes[process_name](
                    config=config,
                    platform=platform,
                    process_index=process_index,
                )
                process.load_parameters(protocol_filename)
                compiled = compile_workflow(process.build_workflow())
                wf_logger = WorkflowLogger(process_name, process_index)
                executor = WorkflowExecutor(
                    compiled,
                    max_workers=4,
                    event_listeners=[
                        lambda e: self._run_store.append_event(e),
                        wf_logger.handle_event,
                    ],
                    error_resilient=error_resilient,
                    process_key=f"{process_name}_{process_index}",
                    cancellation_check=(
                        cancellation_token.is_set
                        if cancellation_token is not None
                        else None
                    ),
                    request_input=request_input,
                )
                result = executor.execute(process, start_node="start")
                self._run_store.append_result(result)
                if not error_resilient and result.errors:
                    raise RuntimeError(
                        f"Process '{process_name}' step {process_index} failed with "
                        f"{len(result.errors)} node error(s)."
                    )
            self._run_store.set_state(success=True)
        except Exception:
            self._run_store.set_state(success=False)
        finally:
            if self._monitoring_service is not None:
                self._monitoring_service.on_run_finished()
            logger.remove(sink_id)

    @staticmethod
    def _parse_sequence(data: dict) -> list[tuple[str, int]]:
        """Extract the ordered (process_name, index) list from protocol key order."""
        sequence = []
        for key in data:
            if key == "main_parameter":
                continue
            m = re.fullmatch(r"(.+)_(\d+)", key)
            if m:
                sequence.append((m.group(1), int(m.group(2))))
        return sequence
