"""Repeated execution keeps accepted alias values and releases failed startup claims."""

from unittest.mock import MagicMock

import networkx as nx
import pytest
from pydantic import BaseModel, Field

from chemunited_workflow import Process, WorkflowNodeSpec
from chemunited_workflow.api.run_store import RunState, RunStore
from chemunited_workflow.api.services import runner as runner_module
from chemunited_workflow.api.services.runner import RunnerService
from chemunited_workflow.platform import Platform
from chemunited_workflow.protocol_plan import build_protocol_plan


class AliasedConfig(BaseModel):
    rate: int = Field(default=2, validation_alias="FLOW")


class AliasedMain(BaseModel):
    solvent: str = Field(default="DMF", validation_alias="SOLVENT")


def document():
    return {
        "schema_version": 2,
        "main_parameter": {"SOLVENT": "DMSO"},
        "sequence": [
            {
                "type": "repeat",
                "id": "cycles",
                "count": "2",
                "steps": [
                    {
                        "type": "process",
                        "id": "work",
                        "process": "work",
                        "parameters": {"FLOW": 9},
                    }
                ],
            }
        ],
    }


@pytest.fixture
def setup(tmp_path, monkeypatch):
    observations = []

    class Work(Process[AliasedConfig]):
        def build_workflow(self):
            graph = nx.DiGraph()
            graph.add_node(
                "start",
                **WorkflowNodeSpec(node_id="start", method="start").model_dump(),
            )
            return graph

        def start(self, ctx):
            observations.append((self.config.rate, self.main_parameters.solvent))
            return True

    factory = MagicMock(return_value=Platform())
    monkeypatch.setattr(runner_module.Platform, "from_project_dir", factory)
    store = RunStore(tmp_path)
    runner = RunnerService(
        tmp_path,
        {"work": Work},
        {"work": AliasedConfig},
        store,
        main_parameter_class=AliasedMain,
    )
    plan = build_protocol_plan(document(), {"work": AliasedConfig}, AliasedMain)
    record = store.try_start_record(
        "source.json", protocol_plan=plan.summary(), execution_active=True
    )
    return runner, store, record, plan, observations, factory


def execute(setup):
    runner, _, record, plan, _, _ = setup
    runner._execute(
        record.run_id,
        "source.json",
        plan,
        plan.source_document,
        dry_run=True,
        timeout_commands="1 s",
        error_resilient=False,
        record_monitoring=False,
        run_record=record,
    )


def test_repeated_runtime_models_keep_entered_validation_alias_values(setup):
    execute(setup)
    _, _, record, _, observations, _ = setup
    assert record.state == RunState.FINISHED
    assert observations == [(9, "DMSO"), (9, "DMSO")]
    assert [result.occurrence["cycle"] for result in record.results] == ["1", "2"]
    assert not record.execution_active


@pytest.mark.parametrize("failure", ["directory", "logger"])
def test_log_startup_failure_releases_claim_before_any_platform_use(
    setup, tmp_path, monkeypatch, failure
):
    runner, store, record, _, observations, factory = setup
    if failure == "directory":
        blocked = tmp_path / "blocked"
        blocked.write_text("A file cannot be used as a log directory.")
        monkeypatch.setattr(
            runner_module, "create_run_log_path", lambda *args: blocked / "run.log"
        )
    else:
        monkeypatch.setattr(
            runner_module.logger,
            "add",
            MagicMock(side_effect=OSError("Log unavailable")),
        )

    execute(setup)

    assert record.state == RunState.FAILED
    assert not record.execution_active
    assert observations == []
    factory.assert_not_called()
    assert store.active_run_id is None
    assert not (tmp_path / "run.lock").exists()
    assert store.try_start_record("retry.json") is not None
