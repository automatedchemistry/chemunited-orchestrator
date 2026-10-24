"""The work-server runs without chemunited-core (no ``live`` extra).

Runs in a fresh interpreter in which chemunited-core can't be imported, so a
module-level import of core anywhere on the server's load and run path fails
the test. The live view still records commands, without pictures.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "custom_project"

SCRIPT = r"""
import json, shutil, sys, threading, time
from pathlib import Path

sys.modules["chemunited_core"] = None  # as if the live extra weren't installed
time.sleep = lambda seconds: None  # the example's protocols sleep for show

source, project = Path(sys.argv[1]), Path(sys.argv[2])
shutil.copytree(source, project, ignore=shutil.ignore_patterns("log", "__pycache__"))
(project / "protocols_historic" / "clean_only.json").write_text(
    json.dumps({"main_parameter": {"repetition_ractions": 1}, "clean_0": {}})
)

from fastapi.testclient import TestClient
from chemunited_workflow.api import create_api
from chemunited_workflow.api.dependencies import get_project_holder

app = create_api()
client = TestClient(app, client=("127.0.0.1", 51216))
response = client.put("/project/", json={"project_dir": str(project)})
assert response.status_code == 200, response.text
holder = app.dependency_overrides[get_project_holder]()
holder.monitoring_store.try_manual_start()

response = client.post("/run/", json={"protocol": "clean_only.json", "dry_run": True})
assert response.status_code == 202, response.text
state = "running"
for _ in range(600):
    state = client.get("/run/status").json()["state"]
    if state != "running":
        break
    threading.Event().wait(0.05)

changes = holder.device_state.changes_since(0)
print(json.dumps({
    "run": state,
    "state": client.get("/platform/state").json(),
    "statuses": [
        (name, device["status"])
        for change in changes
        for name, device in change.get("devices", {}).items()
    ],
    "core_modules": sorted(
        name for name, module in sys.modules.items()
        if name.startswith("chemunited_core") and module is not None
    ),
}))
"""


def test_the_server_loads_and_runs_without_chemunited_core(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(EXAMPLE), str(tmp_path / "project")],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    report = json.loads(result.stdout.strip().splitlines()[-1])

    assert report["run"] == "finished"
    assert report["core_modules"] == []
    state = report["state"]
    assert state["live"] is True and state["pictures"] is False
    injection = state["devices"]["AS injection"]
    assert injection["status"] == "done"
    assert injection["command"]["name"] == "position"
    assert all(device["picture"] is None for device in state["devices"].values())
    assert ["AS injection", "running"] in report["statuses"]
    assert ["AS injection", "done"] in report["statuses"]
