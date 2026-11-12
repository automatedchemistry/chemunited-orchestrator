"""RunnerService — parses protocols and drives workflow execution."""

from __future__ import annotations

import json
import re
import threading
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel

from chemunited_workflow import Process, WorkflowExecutor, compile_workflow
from chemunited_workflow.background import STOP_TIMEOUT_SECONDS, BackgroundTasks
from chemunited_workflow.cancellation import wait_for_operator_input, wait_while_paused
from chemunited_workflow.durations import parse_timeout_commands
from chemunited_workflow.models import WorkflowExecutionEvent
from chemunited_workflow.platform import Platform
from chemunited_workflow.protocol_plan import ProtocolPlan, build_protocol_plan
from chemunited_workflow.provenance import GitState, read_head
from chemunited_workflow.terminal import WorkflowLogger, create_run_log_path

from ..device_state import DeviceStateStore
from ..run_manifest import (
    build_run_manifest,
    finish_run_manifest,
    manifest_path,
    write_run_manifest,
)
from ..run_store import RunRecord, RunStore
from .monitoring import MonitoringService


class RunnerService:
    def __init__(
        self,
        project_dir: Path,
        processes: dict[str, type[Process]],
        configs: dict[str, type[BaseModel]],
        run_store: RunStore,
        monitoring_service: MonitoringService | None = None,
        device_state: DeviceStateStore | None = None,
        git_state: GitState | None = None,
        main_parameter_class: type[BaseModel] | None = None,
    ) -> None:
        self._project_dir = project_dir
        self._processes = processes
        self._configs = configs
        self._run_store = run_store
        self._monitoring_service = monitoring_service
        self._device_state = device_state
        # The project's git state when it was loaded, and so its process code.
        self._git_state = git_state
        self._main_parameter_class = main_parameter_class

    def _plan(self, data: dict) -> ProtocolPlan:
        return build_protocol_plan(
            data,
            {
                name: config
                for name, config in self._configs.items()
                if name in self._processes
            },
            self._main_parameter_class,
        )

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
        if (
            Path(protocol_filename).name != protocol_filename
            or "\\" in protocol_filename
        ):
            raise ValueError("Protocol must be a filename in protocols_historic.")
        protocol_path = self._project_dir / "protocols_historic" / protocol_filename
        data = json.loads(protocol_path.read_text(encoding="utf-8"))
        plan = self._plan(data)
        record = self._run_store.try_start_record(
            protocol_filename,
            protocol_plan=plan.summary(),
            execution_active=True,
        )
        if record is None:
            return None
        try:
            thread = threading.Thread(
                target=self._execute,
                args=(
                    record.run_id,
                    protocol_filename,
                    plan,
                    plan.source_document,
                    dry_run,
                    timeout_commands,
                    error_resilient,
                    record_monitoring,
                    record,
                ),
                daemon=True,
            )
            thread.start()
        except Exception:
            self._run_store.set_state(success=False, record=record)
            self._run_store.release_execution(record)
            raise
        return record.run_id

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
        sequence: ProtocolPlan | list[tuple[str, int]],
        data: dict,
        dry_run: bool,
        timeout_commands: str,
        error_resilient: bool,
        record_monitoring: bool,
        run_record: RunRecord | None = None,
    ) -> None:
        # This run's record, kept rather than looked up again at the end: once
        # the run has ended, another one can start and replace it in the store.
        run_record = run_record if run_record is not None else self._run_store.get()
        if run_record is None or not self._run_store.mark_execution(run_record):
            return
        started_at = run_record.started_at
        try:
            log_path = create_run_log_path(
                self._project_dir, protocol_filename, started_at
            )
            log_path.parent.mkdir(parents=True, exist_ok=True)
            sink_id = logger.add(
                log_path,
                level="DEBUG",
                format="{time:YYYY-MM-DDTHH:mm:ss} | {level: <8} | {message}",
                colorize=False,
                encoding="utf-8",
            )
        except Exception:
            self._run_store.set_state(success=False, record=run_record)
            self._run_store.release_execution(run_record)
            logger.exception("Could not initialize the run log")
            return
        manifest_file = manifest_path(self._project_dir, run_id)
        manifest: dict[str, Any] | None = None
        background = BackgroundTasks()
        cancellation_token = run_record.cancel_event
        plan = sequence if isinstance(sequence, ProtocolPlan) else None
        try:
            try:
                manifest = build_run_manifest(
                    run_id=run_id,
                    started_at=started_at,
                    protocol_filename=protocol_filename,
                    protocol=data,
                    options={
                        "dry_run": dry_run,
                        "timeout_commands": timeout_commands,
                        "error_resilient": error_resilient,
                        "record_monitoring": record_monitoring,
                    },
                    project_name=self._project_dir.name,
                    git=self._git_state,
                    head_at_start=self._head_if_moved(),
                    protocol_plan=plan.summary() if plan is not None else None,
                )
                write_run_manifest(manifest_file, manifest)
                if plan is None:
                    if not isinstance(sequence, list):
                        raise TypeError(
                            "Expected a ProtocolPlan or a list of process steps."
                        )
                    # Retain the private legacy execution entry point used by
                    # integrations, but route it through the same validated model.
                    selected = {"main_parameter": data.get("main_parameter", {})}
                    for name, index in sequence:
                        key = f"{name}_{index}"
                        selected[key] = data.get(key, {})
                    plan = self._plan(selected)
                    manifest["protocol_plan"] = plan.summary()
                    write_run_manifest(manifest_file, manifest)
                self._run_store.set_protocol_plan(plan.summary(), record=run_record)
                pool_dir = self._project_dir / "log" / "pool"
                if pool_dir.exists():
                    for f in pool_dir.glob("*.jsonl"):
                        f.unlink(missing_ok=True)
                pause_event = run_record.pause_event

                def request_input(
                    process_key: str,
                    node_id: str,
                    message: str,
                    timeout_seconds: float,
                ) -> str:
                    input_key = f"{process_key}::{node_id}"
                    event = self._run_store.request_input(
                        input_key, message, record=run_record
                    )
                    try:
                        wait_for_operator_input(
                            event, cancellation_token, timeout_seconds
                        )
                    except Exception:
                        self._run_store.pop_input_value(input_key, record=run_record)
                        raise
                    return (
                        self._run_store.pop_input_value(input_key, record=run_record)
                        or ""
                    )

                def record_occurrence_event(
                    event: WorkflowExecutionEvent, *, metadata: dict[str, Any]
                ) -> None:
                    self._run_store.append_event(
                        replace(event, occurrence=dict(metadata)), record=run_record
                    )

                if cancellation_token.is_set():
                    return
                platform = Platform.from_project_dir(
                    self._project_dir,
                    dry_run=dry_run,
                    log_dir=self._project_dir / "log",
                    timeout_commands=timeout_commands,
                    error_resilient=error_resilient,
                    cancellation_token=cancellation_token,
                    pause_event=pause_event,
                    command_observer=(
                        self._device_state.observer(run_id)
                        if self._device_state is not None
                        else None
                    ),
                )
                if self._monitoring_service is not None:
                    self._monitoring_service.on_run_started(
                        run_id, record=record_monitoring
                    )
                for occurrence in plan.iter_occurrences():
                    # Honor a pause requested between processes, not just mid-node.
                    wait_while_paused(pause_event, cancellation_token)
                    if cancellation_token.is_set():
                        return
                    process_name = occurrence.process_name
                    process_index = occurrence.process_index
                    metadata = occurrence.metadata()
                    self._run_store.set_current_occurrence(metadata, record=run_record)
                    config = self._configs[process_name].model_validate(
                        occurrence.parameters,
                        by_name=True,
                    )
                    process = self._processes[process_name](
                        config=config,
                        platform=platform,
                        process_index=process_index,
                    )
                    if self._main_parameter_class is not None:
                        process.main_parameters = (
                            self._main_parameter_class.model_validate(
                                occurrence.main_parameters,
                                by_name=True,
                            )
                        )
                    compiled = compile_workflow(process.build_workflow())
                    wf_logger = WorkflowLogger(process_name, process_index)
                    executor = WorkflowExecutor(
                        compiled,
                        max_workers=4,
                        event_listeners=[
                            partial(record_occurrence_event, metadata=metadata),
                            wf_logger.handle_event,
                        ],
                        error_resilient=error_resilient,
                        process_key=occurrence.execution_key,
                        cancellation_check=(
                            cancellation_token.is_set
                            if cancellation_token is not None
                            else None
                        ),
                        request_input=partial(request_input, occurrence.execution_key),
                        background=background,
                    )
                    result = executor.execute(process, start_node="start")
                    result.occurrence = metadata
                    self._run_store.append_result(result, record=run_record)
                    if not error_resilient and result.errors:
                        raise RuntimeError(
                            f"Process '{process_name}' step {process_index} failed "
                            f"with {len(result.errors)} node error(s)."
                        )
            finally:
                # Runs on finish, failure and cancel alike — before the final
                # state is set, so the run reads as active until background
                # nodes have actually stopped.
                self._stop_background(background, cancellation_token)
            self._run_store.set_state(success=True, record=run_record)
        except Exception:
            logger.exception("Protocol execution failed")
            self._run_store.set_state(success=False, record=run_record)
        finally:
            try:
                if self._monitoring_service is not None:
                    self._monitoring_service.on_run_finished()
                if manifest is not None:
                    write_run_manifest(
                        manifest_file, finish_run_manifest(manifest, run_record)
                    )
            finally:
                logger.remove(sink_id)
                self._run_store.release_execution(run_record)

    def _head_if_moved(self) -> str | None:
        """HEAD now, if it moved since the project was loaded; None otherwise."""
        if self._git_state is None:
            return None
        head = read_head(self._project_dir)
        if head is None or head == self._git_state.commit:
            return None
        logger.warning(
            "The project's git HEAD moved to {} after the project was loaded: this "
            "run executes the process code loaded at {}. Refresh the project to run "
            "the new code.",
            head[:7],
            self._git_state.commit[:7],
        )
        return head

    @staticmethod
    def _stop_background(
        background: BackgroundTasks, cancellation_token: threading.Event | None
    ) -> None:
        """Stop every background node started during the run and wait for them.

        Trips the run's cancellation token directly rather than calling
        ``RunStore.cancel()``: the run state is left alone (a finished
        protocol still ends FINISHED), but ``platform._wait``, device calls,
        operator-input waits and ``ctx.stop_requested`` all wake up at once.
        Only run-scoped objects watch this token, and the main protocol is
        already done by this point.
        """
        if not background.has_tasks:
            return
        if cancellation_token is not None:
            cancellation_token.set()
        stuck = background.join(STOP_TIMEOUT_SECONDS)
        if stuck:
            logger.warning(
                "Background node(s) did not stop within {}s and were abandoned: {}",
                STOP_TIMEOUT_SECONDS,
                ", ".join(stuck),
            )

    @staticmethod
    def _parse_sequence(data: dict) -> list[tuple[str, int]]:
        """Extract the ordered (process_name, index) list from protocol key order."""
        if "schema_version" in data or "sequence" in data:
            raise ValueError("Versioned protocols require the shared protocol planner.")
        sequence = []
        for key in data:
            if key == "main_parameter":
                continue
            m = re.fullmatch(r"(.+)_(\d+)", key)
            if m:
                sequence.append((m.group(1), int(m.group(2))))
        return sequence
