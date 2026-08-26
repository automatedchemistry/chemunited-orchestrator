"""Integration tests for the /export routes."""

from __future__ import annotations

import importlib.util
import io
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chemunited_workflow.api import create_api
from tests.helpers import make_project_tree

FIXTURES = Path(__file__).parent.parent / "fixtures"

RUN1_LOG = "test_2026-01-01T00-00-00_executed_2026-01-02T10-00-00.log"
RUN1_ID = "test_2026-01-01T00-00-00_2026-01-02T10-00-00"
RUN2_LOG = "test_2026-01-01T00-00-00_executed_2026-01-03T11-00-00.log"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_hook(tmp_path: Path, body: str) -> None:
    hook_dir = tmp_path / "customizations" / "export"
    hook_dir.mkdir(parents=True, exist_ok=True)
    (hook_dir / "export_hook.py").write_text(body, encoding="utf-8")


@pytest.fixture
def project(tmp_path):
    dirs = make_project_tree(tmp_path)
    (dirs["connectivity_dir"] / "associations.json").write_text(
        (FIXTURES / "associations.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (dirs["historic_dir"] / "test_2026-01-01T00-00-00.json").write_text(
        "{}", encoding="utf-8"
    )
    (dirs["log_dir"] / RUN1_LOG).write_text("log1", encoding="utf-8")
    monitoring_dir = dirs["log_dir"] / "monitoring" / RUN1_ID
    monitoring_dir.mkdir(parents=True)
    (monitoring_dir / "chiller__temperature.jsonl").write_text(
        '{"tick": 0, "value": 20}\n', encoding="utf-8"
    )
    (dirs["log_dir"] / RUN2_LOG).write_text("log2", encoding="utf-8")
    return {"dirs": dirs, "tmp_path": tmp_path}


def _make_app_with_project(project):
    from chemunited_workflow.api.dependencies import get_project_holder
    from chemunited_workflow.project_loader import ProjectModules

    proc_dir = project["dirs"]["process_dir"]
    mod = _load_module(proc_dir / "my_process.py", "my_process_export")
    main_mod = _load_module(proc_dir / "main_parameters.py", "main_parameters_export")

    api = create_api()
    holder = api.dependency_overrides[get_project_holder]()
    holder.load(
        ProjectModules(
            project_dir=project["tmp_path"],
            processes={"my_process": mod.MyProcess},
            configs={"my_process": mod.MyConfig},
            main_parameter_class=main_mod.MainParameter,
        )
    )
    return api


@pytest.fixture
def app(project):
    return _make_app_with_project(project)


@pytest.fixture
def client(app):
    return TestClient(app)


# ── no project loaded ────────────────────────────────────────────────────────


def test_preview_returns_503_when_no_project_loaded():
    client = TestClient(create_api())
    r = client.get("/export/preview")
    assert r.status_code == 503


def test_download_returns_503_when_no_project_loaded():
    client = TestClient(create_api())
    r = client.get("/export/download", params={"log": "x.log"})
    assert r.status_code == 503


def test_clean_returns_503_when_no_project_loaded():
    client = TestClient(create_api())
    r = client.post("/export/clean", json={"logs": ["x.log"]})
    assert r.status_code == 503


# ── GET /export/preview ──────────────────────────────────────────────────────


def test_preview_returns_one_row_per_log_with_correlation(client):
    r = client.get("/export/preview")
    assert r.status_code == 200
    rows = {row["log"]["filename"]: row for row in r.json()}

    assert set(rows) == {RUN1_LOG, RUN2_LOG}

    run1 = rows[RUN1_LOG]
    assert run1["monitoring"]["run_id"] == RUN1_ID
    assert [f["filename"] for f in run1["monitoring"]["files"]] == [
        f"{RUN1_ID}/chiller__temperature.jsonl"
    ]
    assert run1["protocol"]["filename"] == "test_2026-01-01T00-00-00.json"

    run2 = rows[RUN2_LOG]
    assert run2["monitoring"] is None
    assert run2["protocol"]["filename"] == "test_2026-01-01T00-00-00.json"


# ── GET /export/download ─────────────────────────────────────────────────────


def test_download_requires_at_least_one_log(client):
    r = client.get("/export/download")
    assert r.status_code == 422


def test_download_returns_a_valid_zip_scoped_to_selection(client):
    r = client.get("/export/download", params={"log": RUN1_LOG})
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    assert "attachment" in r.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        assert set(zf.namelist()) == {
            f"log/{RUN1_LOG}",
            f"log/monitoring/{RUN1_ID}/chiller__temperature.jsonl",
            "protocols_historic/test_2026-01-01T00-00-00.json",
        }


def test_download_dedupes_shared_protocol_across_selected_runs(client):
    r = client.get("/export/download", params=[("log", RUN1_LOG), ("log", RUN2_LOG)])
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = zf.namelist()
    assert names.count("protocols_historic/test_2026-01-01T00-00-00.json") == 1


def test_download_never_deletes_source_files(client, project):
    client.get("/export/download", params={"log": RUN1_LOG})
    assert (project["dirs"]["log_dir"] / RUN1_LOG).exists()


# ── POST /export/clean ───────────────────────────────────────────────────────


def test_clean_requires_at_least_one_log(client):
    r = client.post("/export/clean", json={"logs": []})
    assert r.status_code == 422


def test_clean_deletes_only_selected_run_and_preview_reflects_it(client, project):
    r = client.post("/export/clean", json={"logs": [RUN1_LOG]})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert not (project["dirs"]["log_dir"] / RUN1_LOG).exists()
    assert (project["dirs"]["log_dir"] / RUN2_LOG).exists()

    rows = {row["log"]["filename"] for row in client.get("/export/preview").json()}
    assert rows == {RUN2_LOG}


def test_clean_never_touches_protocols_historic(client, project):
    client.post("/export/clean", json={"logs": [RUN1_LOG, RUN2_LOG]})
    assert (project["dirs"]["historic_dir"] / "test_2026-01-01T00-00-00.json").exists()


def test_clean_uses_custom_hook(client, project):
    _write_hook(
        project["tmp_path"],
        "def clean(project_dir, logs):\n"
        "    return {'deleted': ['custom.txt'], 'count': 1}\n"
        "EXPORT_HOOKS = {'clean': clean}\n",
    )
    r = client.post("/export/clean", json={"logs": [RUN1_LOG]})
    assert r.status_code == 200
    assert r.json() == {"deleted": ["custom.txt"], "count": 1}
    # the default clean never ran, so the real log file is untouched
    assert (project["dirs"]["log_dir"] / RUN1_LOG).exists()


def test_clean_hook_exception_returns_500(client, project):
    _write_hook(
        project["tmp_path"],
        "def clean(project_dir, logs):\n    raise ValueError('nope')\n"
        "EXPORT_HOOKS = {'clean': clean}\n",
    )
    r = client.post("/export/clean", json={"logs": [RUN1_LOG]})
    assert r.status_code == 500
