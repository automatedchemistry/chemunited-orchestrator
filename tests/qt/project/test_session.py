from __future__ import annotations

import json
import zipfile
from textwrap import dedent

import pytest

from chemunited.qt.project.manifest import ProjectManifest
from chemunited.qt.project.session import ProjectSession
from chemunited.qt.protocols.workflows import ProcessWorkflow


def _write_project(working_dir, draw_content: str) -> None:
    working_dir.mkdir(parents=True, exist_ok=True)
    ProjectManifest(
        name=working_dir.name,
        chemunited_version="0.1.0",
    ).save(working_dir)
    draw_path = working_dir / "draw" / "setup.py"
    draw_path.parent.mkdir(parents=True, exist_ok=True)
    draw_path.write_text(draw_content, encoding="utf-8")


def _write_archive(archive_path, project_name: str, draw_content: str) -> None:
    manifest = {
        "name": project_name,
        "chemunited_version": "0.1.0",
        "processes_order": [],
    }
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("draw/setup.py", draw_content)


def test_import_chemunited_prefers_existing_project_directory(tmp_path):
    archive_path = tmp_path / "demo.chemunited"
    working_dir = tmp_path / "demo"
    local_draw = "# local project folder\n"
    archived_draw = "# archived export\n"
    _write_archive(archive_path, "demo", archived_draw)
    _write_project(working_dir, local_draw)

    session = ProjectSession()
    session.import_chemunited(archive_path)

    assert session.working_dir == working_dir
    assert session.source_file == archive_path
    assert (working_dir / "draw" / "setup.py").read_text(encoding="utf-8") == local_draw


def test_import_chemunited_does_not_overwrite_existing_non_project_path(tmp_path):
    archive_path = tmp_path / "demo.chemunited"
    working_dir = tmp_path / "demo"
    notes_path = working_dir / "notes.txt"
    _write_archive(archive_path, "demo", "# archived export\n")
    working_dir.mkdir()
    notes_path.write_text("keep me", encoding="utf-8")

    session = ProjectSession()
    with pytest.raises(FileExistsError):
        session.import_chemunited(archive_path)

    assert notes_path.read_text(encoding="utf-8") == "keep me"
    assert not (working_dir / "draw" / "setup.py").exists()


def test_sync_process_creates_new_process_file(tmp_path):
    session = ProjectSession()
    session.new(name="demo", location=tmp_path, init_git=False)
    workflow = ProcessWorkflow("React")
    workflow.add_block(
        node_id="script_1",
        method="script_1",
        position=(100.0, 100.0),
    )
    workflow.add_connection("start", "script_1")
    workflow.add_connection("script_1", "end")

    synced = session.sync_process("React", workflow)

    content = (tmp_path / "demo" / "protocols" / "React.py").read_text(
        encoding="utf-8"
    )
    assert synced is True
    assert "class ReactProcess(Process[ReactProcessConfig]):" in content
    assert 'def script_1(self, ctx: NodeExecutionContext) -> bool:' in content


def test_sync_process_updates_existing_file_in_place(tmp_path):
    session = ProjectSession()
    session.new(name="demo", location=tmp_path, init_git=False)
    working_dir = tmp_path / "demo"
    process_path = working_dir / "protocols" / "React.py"
    process_path.parent.mkdir(parents=True, exist_ok=True)
    process_path.write_text(
        dedent(
            """
            from __future__ import annotations

            import networkx as nx
            from pydantic import BaseModel, ConfigDict

            from chemunited.workflow import (
                NodeExecutionContext,
                Process,
                WorkflowEdgeSpec,
                WorkflowNodeSpec,
            )


            class ReactProcessConfig(BaseModel):
                model_config = ConfigDict(frozen=True)


            class ReactProcess(Process[ReactProcessConfig]):
                \"\"\"React\"\"\"

                __process_label__ = "React"
                __process_description__ = ""

                def build_workflow(self) -> nx.DiGraph:
                    graph = nx.DiGraph()

                    graph.add_node(
                        "start",
                        **WorkflowNodeSpec(
                            node_id="start",
                            method="start",
                            position=(0.0, 0.0),
                        ).model_dump(exclude_none=True),
                    )

                    graph.add_node(
                        "keep_node",
                        **WorkflowNodeSpec(
                            node_id="keep_node",
                            method="keep_step",
                            position=(100.0, 0.0),
                        ).model_dump(exclude_none=True),
                    )

                    graph.add_node(
                        "obsolete_node",
                        **WorkflowNodeSpec(
                            node_id="obsolete_node",
                            method="obsolete_step",
                            position=(200.0, 0.0),
                        ).model_dump(exclude_none=True),
                    )

                    graph.add_node(
                        "end",
                        **WorkflowNodeSpec(
                            node_id="end",
                            method="finish",
                            position=(300.0, 0.0),
                        ).model_dump(exclude_none=True),
                    )

                    graph.add_edge(
                        "start",
                        "keep_node",
                        **WorkflowEdgeSpec(
                            condition=True,
                        ).model_dump(exclude_none=True),
                    )

                    graph.add_edge(
                        "keep_node",
                        "obsolete_node",
                        **WorkflowEdgeSpec(
                            condition=True,
                        ).model_dump(exclude_none=True),
                    )

                    graph.add_edge(
                        "obsolete_node",
                        "end",
                        **WorkflowEdgeSpec(
                            condition=True,
                        ).model_dump(exclude_none=True),
                    )

                    return graph

                # Existing workflow methods

                def start(self, ctx: NodeExecutionContext) -> bool:
                    ctx.runtime.status_message = "Custom start"
                    return True

                def keep_step(self, ctx: NodeExecutionContext) -> bool:
                    ctx.runtime.status_message = "Keep exact body"
                    return True

                def obsolete_step(self, ctx: NodeExecutionContext) -> bool:
                    ctx.runtime.status_message = "Remove exact body"
                    return True

                def _prepare_stock(self) -> str:
                    return "helper"

                def finish(self, ctx: NodeExecutionContext) -> bool:
                    ctx.runtime.status_message = "Custom finish"
                    return True
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    workflow = ProcessWorkflow("React")
    workflow.add_block(
        node_id="keep_node",
        method="keep_step",
        position=(120.0, 0.0),
    )
    workflow.add_block(
        node_id="fresh_node",
        method="fresh_step",
        position=(240.0, 0.0),
    )
    workflow.add_connection("start", "keep_node")
    workflow.add_connection("keep_node", "fresh_node")
    workflow.add_connection("fresh_node", "end")

    synced = session.sync_process("React", workflow)

    updated = process_path.read_text(encoding="utf-8")
    assert synced is True
    assert '"fresh_node"' in updated
    assert '"obsolete_node"' not in updated
    assert "def keep_step(self, ctx: NodeExecutionContext) -> bool:" in updated
    assert 'ctx.runtime.status_message = "Keep exact body"' in updated
    assert '"Custom start"' in updated
    assert '"Custom finish"' in updated
    assert "def obsolete_step(" not in updated
    assert 'def fresh_step(self, ctx: NodeExecutionContext) -> bool:' in updated
    assert 'ctx.runtime.status_message = "Fresh Step ran."' in updated
    assert 'def _prepare_stock(self) -> str:' in updated


def test_sync_process_leaves_invalid_existing_file_unchanged(tmp_path):
    session = ProjectSession()
    session.new(name="demo", location=tmp_path, init_git=False)
    working_dir = tmp_path / "demo"
    process_path = working_dir / "protocols" / "React.py"
    process_path.parent.mkdir(parents=True, exist_ok=True)
    original = "class DifferentProcess:\n    pass\n"
    process_path.write_text(original, encoding="utf-8")
    workflow = ProcessWorkflow("React")

    synced = session.sync_process("React", workflow)

    assert synced is False
    assert process_path.read_text(encoding="utf-8") == original
