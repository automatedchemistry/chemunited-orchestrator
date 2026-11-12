"""Save, preview, execute and restore a native repeated protocol via the API."""

from __future__ import annotations

import json
import time

import networkx as nx
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from tests.helpers import LOOPBACK_CLIENT

from chemunited_workflow import Process, WorkflowNodeSpec
from chemunited_workflow.api import create_api
from chemunited_workflow.api.dependencies import get_project_holder
from chemunited_workflow.api.run_manifest import manifest_path
from chemunited_workflow.project_loader import ProjectModules


class DelayConfig(BaseModel):
    seconds: float = Field(default=1, ge=0)


class Main(BaseModel):
    label: str = "resolved default"


class Delay(Process[DelayConfig]):
    calls: list[float] = []

    def build_workflow(self):
        graph = nx.DiGraph()
        graph.add_node(
            "start",
            **WorkflowNodeSpec(node_id="start", method="delay").model_dump(
                exclude_none=True
            ),
        )
        return graph

    def delay(self, ctx):
        self.calls.append(self.config.seconds)
        ctx.report_progress(0, "Waiting", wait_seconds=self.config.seconds)
        self.platform._wait(self.config.seconds)
        ctx.report_progress(100, "Delay completed")
        return True


def _document():
    return {
        "schema_version": 2,
        "main_parameter": {},
        "sequence": [
            {
                "type": "repeat",
                "id": "group",
                "label": "Delays",
                "count": "3",
                "steps": [
                    {
                        "type": "process",
                        "id": "inner",
                        "process": "delay",
                        "parameters": {"seconds": 1},
                    }
                ],
            },
            {
                "type": "process",
                "id": "closing",
                "process": "delay",
                "parameters": {"seconds": 2},
            },
        ],
    }


def test_repeat_delay_save_preview_run_report_and_snapshot_reload(tmp_path):
    (tmp_path / "connectivity").mkdir()
    (tmp_path / "connectivity" / "associations.json").write_text(
        '{"associations": []}', encoding="utf-8"
    )
    (tmp_path / "protocols_historic").mkdir()
    app = create_api()
    holder = app.dependency_overrides[get_project_holder]()
    holder.load(
        ProjectModules(tmp_path, {"delay": Delay}, {"delay": DelayConfig}, Main)
    )
    Delay.calls = []
    with TestClient(app, client=LOOPBACK_CLIENT) as client:
        saved = client.post(
            "/protocols/", json={"name": "repeated-delay", "data": _document()}
        )
        assert saved.status_code == 201, saved.text
        filename = saved.json()["filename"]
        assert client.get(f"/protocols/{filename}").json() == _document()
        summary = client.get(f"/protocols/{filename}/plan").json()
        assert summary["total_executions"] == "4"
        preview = client.post(
            "/protocols/preview", json={"data": _document(), "offset": "2", "limit": 2}
        ).json()
        assert [row["cycle"] for row in preview["occurrences"]] == ["3", None]
        start = client.post("/run/", json={"protocol": filename, "dry_run": True})
        assert start.status_code == 202, start.text
        run_id = start.json()["run_id"]
        active = client.get("/run/active").json()
        assert active["protocol_plan"]["document"] == _document()
        # Active UI/reporting and future cycles must survive this file deletion.
        (tmp_path / "protocols_historic" / filename).unlink()
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            status = client.get("/run/status").json()
            if status["state"] not in ("running", "paused"):
                break
            time.sleep(0.025)
        assert status["state"] == "finished", status
        assert status["protocol"] == filename
        assert status["protocol_plan"]["document"] == _document()
        assert Delay.calls == [1, 1, 1, 2]
        report = client.get("/run/report").json()
        assert [item["process"] for item in report["results"]] == [
            "delay_0",
            "delay_1",
            "delay_2",
            "delay_3",
        ]
        assert [item["occurrence"]["cycle"] for item in report["results"]] == [
            "1",
            "2",
            "3",
            None,
        ]
        assert status["events"]
        assert all(
            event["occurrence"]["execution_key"] == event["process"]
            for event in status["events"]
        )
        stream = client.get("/run/stream").text
        assert '"cycle": "3"' in stream
        assert '"state": "finished"' in stream
        while holder.run_store.get().execution_active and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not holder.run_store.get().execution_active
    manifest = json.loads(manifest_path(tmp_path, run_id).read_text(encoding="utf-8"))
    assert manifest["protocol_plan"]["resolved_document"]["main_parameter"] == {
        "label": "resolved default"
    }
    assert len(manifest["results"]) == 4
