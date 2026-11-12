"""Native repeats execute real workflows using one accepted, resolved snapshot."""

from __future__ import annotations

import json
import threading
from unittest.mock import MagicMock

import networkx as nx
import pytest
from pydantic import BaseModel, Field

from chemunited_workflow import Process, WorkflowEdgeSpec, WorkflowNodeSpec
from chemunited_workflow.api.run_manifest import manifest_path
from chemunited_workflow.api.run_store import RunState, RunStore
from chemunited_workflow.api.services import runner as runner_module
from chemunited_workflow.api.services.runner import RunnerService
from chemunited_workflow.protocol_plan import build_protocol_plan


class Config(BaseModel):
    name: str = "body"
    values: list[int] = Field(default_factory=lambda: [7])
    fail: bool = False


class Main(BaseModel):
    solvent: str = "DMF"


class RecordingProcess(Process[Config]):
    observed: list[tuple[str, list[int], str]] = []
    cancel_after: int | None = None
    store: RunStore | None = None

    def build_workflow(self):
        graph = nx.DiGraph()
        for name in ("start", "end"):
            graph.add_node(
                name,
                **WorkflowNodeSpec(node_id=name, method=name).model_dump(
                    exclude_none=True
                ),
                block_tag=name,
            )
        graph.add_edge(
            "start",
            "end",
            **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
        )
        return graph

    def start(self, ctx):
        self.observed.append(
            (self.config.name, list(self.config.values), self.main_parameters.solvent)
        )
        self.config.values.append(99)
        if self.cancel_after == len(self.observed):
            self.store.cancel("test boundary stop")
        if self.config.fail:
            raise RuntimeError("deliberate process failure")
        return True

    def end(self, ctx):
        return True


def step(source_id="body", **parameters):
    return {
        "type": "process",
        "id": source_id,
        "process": "record",
        "parameters": parameters,
    }


def document(count="3", *, body=None):
    return {
        "schema_version": 2,
        "main_parameter": {},
        "sequence": [
            step("before", name="before"),
            {
                "type": "repeat",
                "id": "repeat",
                "label": "Assembly",
                "count": count,
                "steps": body or [step()],
            },
            step("after", name="after"),
        ],
    }


@pytest.fixture
def runner(tmp_path):
    (tmp_path / "connectivity").mkdir()
    (tmp_path / "connectivity" / "associations.json").write_text(
        '{"associations": []}', encoding="utf-8"
    )
    (tmp_path / "protocols_historic").mkdir()
    store = RunStore()
    RecordingProcess.observed = []
    RecordingProcess.cancel_after = None
    RecordingProcess.store = store
    svc = RunnerService(
        tmp_path,
        {"record": RecordingProcess},
        {"record": Config},
        store,
        main_parameter_class=Main,
    )
    return svc, store, tmp_path


def execute(runner, data, *, resilient=False):
    svc, store, _ = runner
    plan = build_protocol_plan(data, {"record": Config}, Main)
    run_id = store.try_start("repeat.json", protocol_plan=plan.summary())
    svc._execute(
        run_id,
        "repeat.json",
        plan,
        plan.source_document,
        dry_run=True,
        timeout_commands="1 s",
        error_resilient=resilient,
        record_monitoring=False,
    )
    return store.get()


def test_repeats_keep_order_defaults_fresh_state_and_unique_provenance(runner):
    record = execute(runner, document())
    assert record.state == RunState.FINISHED
    assert [row[0] for row in RecordingProcess.observed] == [
        "before",
        "body",
        "body",
        "body",
        "after",
    ]
    assert all(
        values == [7] and solvent == "DMF"
        for _, values, solvent in RecordingProcess.observed
    )
    assert [result.process for result in record.results] == [
        f"record_{index}" for index in range(5)
    ]
    assert [result.occurrence["cycle"] for result in record.results] == [
        None,
        "1",
        "2",
        "3",
        None,
    ]
    assert all(
        event.occurrence["execution_key"] == event.process for event in record.events
    )
    manifest = json.loads(manifest_path(runner[2], record.run_id).read_text())
    assert manifest["protocol"]["content"] == document()
    assert manifest["protocol_plan"]["total_executions"] == "5"
    assert manifest["protocol_plan"]["resolved_document"]["main_parameter"] == {
        "solvent": "DMF"
    }
    assert manifest["results"][2]["occurrence"]["cycle"] == "2"


def test_huge_repeat_can_stop_after_few_occurrences(runner):
    RecordingProcess.cancel_after = 4
    record = execute(runner, document("9007199254740993123456789"))
    assert record.state == RunState.CANCELLED
    assert len(RecordingProcess.observed) == 4
    assert record.current_occurrence["cycle"] == "3"
    assert record.protocol_plan["total_executions"] == "9007199254740993123456791"


@pytest.mark.parametrize("resilient", [False, True])
def test_bad_repeat_rejected_before_slot_platform_or_monitoring(
    runner, monkeypatch, resilient
):
    svc, store, path = runner
    (path / "protocols_historic" / "bad.json").write_text(
        json.dumps(document("1")), encoding="utf-8"
    )
    platform_factory = MagicMock()
    monkeypatch.setattr(runner_module.Platform, "from_project_dir", platform_factory)
    monitoring = MagicMock()
    svc._monitoring_service = monitoring
    with pytest.raises(ValueError):
        svc.start("bad.json", error_resilient=resilient)
    assert store.get() is None
    platform_factory.assert_not_called()
    monitoring.on_run_started.assert_not_called()


def test_start_snapshot_survives_file_deletion_and_never_uses_historic_loader(
    runner, monkeypatch
):
    svc, store, path = runner
    file = path / "protocols_historic" / "repeat.json"
    file.write_text(json.dumps(document()), encoding="utf-8")
    calls = []

    class CapturedThread:
        def __init__(self, *, target, args, daemon):
            calls.append((target, args))

        def start(self):
            pass

    # Only replace thread construction while accepting the run. Workflow
    # executors themselves must still use actual threads.
    with monkeypatch.context() as patch:
        patch.setattr(runner_module.threading, "Thread", CapturedThread)
        svc.start("repeat.json", dry_run=True)
    file.unlink()
    monkeypatch.setattr(
        RecordingProcess,
        "load_parameters",
        MagicMock(side_effect=AssertionError("historic source reread")),
    )
    target, args = calls[0]
    target(*args)
    assert store.get().state == RunState.FINISHED
    assert len(RecordingProcess.observed) == 5
    RecordingProcess.load_parameters.assert_not_called()


@pytest.mark.parametrize(
    "resilient,expected", [(False, RunState.FAILED), (True, RunState.FINISHED)]
)
def test_repeat_preserves_runtime_error_resilience(runner, resilient, expected):
    record = execute(runner, document(body=[step(fail=True)]), resilient=resilient)
    assert record.state == expected
    assert len(record.results) == (2 if not resilient else 5)
    assert record.results[1].errors


def test_operator_inputs_are_scoped_to_execution_occurrence():
    store = RunStore()
    store.try_start("repeat.json")
    first = store.request_input("record_1::confirm", "Cycle 1")
    second = store.request_input("record_2::confirm", "Cycle 2")
    assert not store.submit_input("confirm", "ambiguous")
    assert store.submit_input("record_2::confirm", "yes")
    assert second.is_set() and not first.is_set()
    assert store.pop_input_value("record_2::confirm") == "yes"


def test_pause_between_cycles_waits_until_resumed(runner, monkeypatch):
    svc, store, _ = runner
    paused = threading.Event()
    original = RecordingProcess.start

    def pause_after_first(self, ctx):
        answer = original(self, ctx)
        if self.config.name == "body" and len(self.observed) == 2:
            store.pause()
            paused.set()
        return answer

    monkeypatch.setattr(RecordingProcess, "start", pause_after_first)
    worker = threading.Thread(
        target=lambda: execute(runner, document("2")), daemon=True
    )
    worker.start()
    assert paused.wait(3)
    assert store.get().state == RunState.PAUSED
    assert len(RecordingProcess.observed) == 2
    store.resume()
    worker.join(5)
    assert not worker.is_alive()
    assert store.get().state == RunState.FINISHED
    assert len(RecordingProcess.observed) == 4


def test_repeated_background_processes_keep_distinct_identity_and_run_lifetime(runner):
    svc, store, _ = runner
    started: dict[int, threading.Event] = {0: threading.Event(), 1: threading.Event()}
    ended = []
    observations = []

    class BackgroundProcess(Process[Config]):
        def build_workflow(self):
            graph = nx.DiGraph()
            for name, tag in (
                ("start", "start"),
                ("monitor", "background"),
                ("end", "end"),
            ):
                graph.add_node(
                    name,
                    **WorkflowNodeSpec(node_id=name, method=name).model_dump(
                        exclude_none=True
                    ),
                    block_tag=tag,
                )
            for target in ("monitor", "end"):
                graph.add_edge(
                    "start",
                    target,
                    **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
                )
            return graph

        def start(self, ctx):
            return True

        def monitor(self, ctx):
            started[self.process_index].set()
            try:
                while not ctx.stop_requested:
                    self.platform._wait(0.01)
            finally:
                ended.append(self.process_index)
            return True

        def end(self, ctx):
            assert started[self.process_index].wait(3)
            observations.append((self.process_index, list(ended)))
            return True

    svc._processes = {"record": BackgroundProcess}
    data = {
        "schema_version": 2,
        "sequence": [
            {"type": "repeat", "id": "repeat", "count": "2", "steps": [step()]}
        ],
    }
    plan = build_protocol_plan(data, {"record": Config}, Main)
    record = store.try_start_record("background.json", protocol_plan=plan.summary())
    svc._execute(
        record.run_id,
        "background.json",
        plan,
        plan.source_document,
        dry_run=True,
        timeout_commands="1 s",
        error_resilient=False,
        record_monitoring=False,
        run_record=record,
    )
    assert record.state == RunState.FINISHED
    assert observations == [(0, []), (1, [])]
    assert sorted(ended) == [0, 1]
    background_events = [
        event
        for event in record.events
        if event.node_key and event.node_key[0] == "monitor"
    ]
    assert {event.process for event in background_events} == {"record_0", "record_1"}
    assert all(
        event.occurrence["cycle"] == str(int(event.process[-1]) + 1)
        for event in background_events
    )
