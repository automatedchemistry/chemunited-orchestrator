"""Save/reopen and paged preview share the planner without hardware or writes on read."""

import json
from copy import deepcopy

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from chemunited_workflow.api.dependencies import get_protocol_service
from chemunited_workflow.api.routers.protocols import read_router, write_router
from chemunited_workflow.api.services.protocol import ProtocolService


class Config(BaseModel):
    amount: int = Field(default=2, ge=0)


class Main(BaseModel):
    title: str = "Experiment"


@pytest.fixture
def setup(tmp_path):
    (tmp_path / "protocols_historic").mkdir()
    service = ProtocolService(tmp_path, {}, {"work": Config}, Main)
    app = FastAPI()
    app.dependency_overrides[get_protocol_service] = lambda: service
    app.include_router(read_router)
    app.include_router(write_router)
    with TestClient(app) as client:
        yield client, service, tmp_path / "protocols_historic"


def document(count="3"):
    return {
        "schema_version": 2,
        "main_parameter": {"title": "Saved experiment"},
        "sequence": [
            {
                "type": "repeat",
                "id": "assembly",
                "label": "Assembly",
                "count": count,
                "steps": [
                    {
                        "type": "process",
                        "id": "shared-work",
                        "process": "work",
                        "parameters": {"amount": 7},
                    },
                ],
            },
            {
                "type": "process",
                "id": "after",
                "process": "work",
                "parameters": {"amount": 9},
            },
        ],
    }


def test_v2_save_reopen_preserves_compact_groups_parameters_and_ids(setup):
    client, service, historic = setup
    source = document("9007199254740993")
    original = deepcopy(source)
    response = client.post("/protocols/", json={"name": "grouped", "data": source})
    assert response.status_code == 201, response.text
    filename = response.json()["filename"]
    saved = json.loads((historic / filename).read_text())
    assert saved == source == original
    assert len(saved["sequence"]) == 2
    assert client.get(f"/protocols/{filename}").json() == source
    summary = client.get(f"/protocols/{filename}/plan").json()
    assert summary["total_executions"] == "9007199254740994"
    assert summary["source_schema_version"] == 2
    assert summary["planner_version"] == 1
    assert summary["source_document"] == source
    page = client.get(
        f"/protocols/{filename}/preview",
        params={"offset": "9007199254740992", "limit": 2},
    ).json()
    assert [item["execution_key"] for item in page["occurrences"]] == [
        "work_9007199254740992",
        "work_9007199254740993",
    ]
    assert page["occurrences"][0]["cycle"] == "9007199254740993"
    assert page["occurrences"][1]["cycle"] is None
    assert page["next_offset"] is None


def test_legacy_read_and_preview_leave_file_unchanged_and_save_emits_v2(setup):
    client, service, historic = setup
    legacy = {"work_9": {"amount": 9}, "work_2": {"amount": 2}}
    path = historic / "old.json"
    original = json.dumps(legacy, indent=3)
    path.write_text(original)
    opened = client.get("/protocols/old.json")
    assert opened.status_code == 200
    assert [step["id"] for step in opened.json()["sequence"]] == ["work_9", "work_2"]
    summary = client.get("/protocols/old.json/plan").json()
    assert summary["source_document"] == legacy
    assert summary["source_schema_version"] == 1
    page = client.get("/protocols/old.json/preview").json()
    assert [item["execution_key"] for item in page["occurrences"]] == [
        "work_9",
        "work_2",
    ]
    assert page["occurrences"][0]["process_index"] == "9"
    assert path.read_text() == original
    result = client.post("/protocols/", json={"name": "resaved", "data": legacy})
    saved = json.loads((historic / result.json()["filename"]).read_text())
    assert saved["schema_version"] == 2
    assert saved["main_parameter"] == {"title": "Experiment"}
    assert [step["id"] for step in saved["sequence"]] == ["work_9", "work_2"]
    assert path.read_text() == original


def test_unsaved_preview_is_bounded_exact_and_has_no_file_side_effects(setup):
    client, service, historic = setup
    source = document("10000000000000000000000000000000000000000")
    result = client.post(
        "/protocols/preview",
        json={
            "data": source,
            "offset": "9999999999999999999999999999999999999998",
            "limit": 2,
        },
    )
    assert result.status_code == 200, result.text
    page = result.json()
    assert len(page["occurrences"]) == 2
    assert page["document"] == source
    assert page["next_offset"] == "10000000000000000000000000000000000000000"
    assert list(historic.iterdir()) == []


@pytest.mark.parametrize(
    "patch",
    [
        {"offset": 9007199254740993},
        {"offset": "01"},
        {"offset": "-1"},
        {"limit": 201},
        {"limit": True},
        {"limit": "20"},
    ],
)
def test_preview_rejects_invalid_pagination_without_precision_coercion(setup, patch):
    client, _, _ = setup
    response = client.post("/protocols/preview", json={"data": document(), **patch})
    assert response.status_code == 422


def test_invalid_settings_fail_save_and_preview_with_source_field(setup):
    client, _, historic = setup
    source = document()
    source["sequence"][0]["steps"][0]["parameters"]["amount"] = -1
    for endpoint, body in (
        ("/protocols/", {"name": "bad", "data": source}),
        ("/protocols/preview", {"data": source}),
    ):
        response = client.post(endpoint, json=body)
        assert response.status_code == 422
        assert all(
            text in response.json()["detail"]
            for text in ("Assembly", "shared-work", "amount")
        )
    assert list(historic.iterdir()) == []


def test_saved_invalid_version_and_missing_files_are_explicit_errors(setup):
    client, _, historic = setup
    (historic / "future.json").write_text(
        json.dumps({"schema_version": 999, "sequence": []})
    )
    for suffix in ("/plan", "/preview"):
        response = client.get(f"/protocols/future.json{suffix}")
        assert response.status_code == 422
        assert "schema_version" in response.json()["detail"]
        assert client.get(f"/protocols/missing.json{suffix}").status_code == 404


def test_hidden_processes_remain_registered_but_marked_out_of_add_library(tmp_path):
    class Legacy:
        library_visible = False

    class Ordinary:
        pass

    service = ProtocolService(
        tmp_path,
        {"legacy": Legacy, "ordinary": Ordinary},
        {"legacy": Config, "ordinary": Config},
        Main,
    )
    listed = service.list_processes()
    assert [(item["name"], item["library_visible"]) for item in listed] == [
        ("legacy", False),
        ("ordinary", True),
    ]
    assert service.build_plan({"legacy_9": {}}).total_executions == 1
    assert service.get_process_schema("legacy")["process"] == "legacy"
