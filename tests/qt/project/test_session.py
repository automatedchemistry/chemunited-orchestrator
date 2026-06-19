from __future__ import annotations

import json
import zipfile
from textwrap import dedent

import pytest

from chemunited.orchestrator.project_file import OrchestratorProjectFile
from chemunited.project.manifest import ProjectManifest
from chemunited.project.session import ProjectSession
from chemunited.protocols.workflows import ProcessWorkflow
from chemunited.shared.enums.protocols_enum import ProtocolBlock
from chemunited.utils.files import load_class


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


def test_protocols_historic_directory_is_created_and_exported(tmp_path):
    session = ProjectSession()
    session.new(name="demo", location=tmp_path, init_git=False)
    working_dir = tmp_path / "demo"
    history_dir = working_dir / "protocols_historic"
    history_file = history_dir / "react.json"

    assert history_dir.is_dir()
    assert not (working_dir / "api.py").exists()

    history_file.write_text('{"process": "react"}\n', encoding="utf-8")
    archive_path = session.export_chemunited(tmp_path / "demo")

    with zipfile.ZipFile(archive_path, "r") as zf:
        assert "protocols_historic/react.json" in zf.namelist()
        assert "api.py" not in zf.namelist()


def test_log_directory_is_created_ignored_and_not_exported(tmp_path):
    session = ProjectSession()
    session.new(name="demo", location=tmp_path, init_git=False)
    working_dir = tmp_path / "demo"
    log_dir = working_dir / "log"
    log_file = log_dir / "react_2026-03-27T16-18-00__2026-03-27T19-20-00.log"

    assert log_dir.is_dir()
    assert "log/" in (working_dir / ".gitignore").read_text(encoding="utf-8")

    log_file.write_text("local execution output\n", encoding="utf-8")
    archive_path = session.export_chemunited(tmp_path / "demo")

    with zipfile.ZipFile(archive_path, "r") as zf:
        assert not any(name.startswith("log/") for name in zf.namelist())


def test_process_load_parameters_uses_process_file_stem(tmp_path):
    working_dir = tmp_path / "demo"
    protocols_dir = working_dir / "protocols"
    protocols_dir.mkdir(parents=True)
    process_path = protocols_dir / "react.py"
    process_path.write_text(
        dedent(
            """
            from __future__ import annotations

            import networkx as nx
            from pydantic import BaseModel, ConfigDict

            from chemunited_workflow import Process


            class ProcessConfig(BaseModel):
                model_config = ConfigDict(frozen=True)

                amount: int = 0


            class CustomProcess(Process[ProcessConfig]):
                def build_workflow(self) -> nx.DiGraph:
                    return nx.DiGraph()
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    history_dir = working_dir / "protocols_historic"
    history_dir.mkdir()
    (history_dir / "parameters.json").write_text(
        json.dumps({"react_0": {"amount": 7}}),
        encoding="utf-8",
    )

    process_cls = load_class(process_path, "CustomProcess")
    config_cls = process_cls.__orig_bases__[0].__args__[0]
    process = process_cls(config_cls())

    assert process.load_parameters() is True
    assert process.config.amount == 7

    (history_dir / "legacy.json").write_text(
        json.dumps({"CustomProcess_0": {"amount": 99}}),
        encoding="utf-8",
    )
    legacy_process = process_cls(config_cls())

    assert legacy_process.load_parameters(historic_file="legacy.json") is False
    assert legacy_process.config.amount == 0


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

    content = (tmp_path / "demo" / "protocols" / "React.py").read_text(encoding="utf-8")
    assert synced is True
    assert "from chemunited_workflow import (" in content
    assert "from chemunited.workflow import" not in content
    assert "class ProcessConfig(BaseModel):" in content
    assert "class CustomProcess(Process[ProcessConfig]):" in content
    assert "# Process name:" not in content
    assert "__process_label__" not in content
    assert "__process_description__" not in content
    assert "def script_1(self, ctx: NodeExecutionContext) -> bool:" in content

    init_content = (tmp_path / "demo" / "protocols" / "__init__.py").read_text(
        encoding="utf-8"
    )
    assert (
        "from .React import CustomProcess as ReactProcess, "
        "ProcessConfig as ReactConfig"
    ) in init_content
    assert '    "React": ReactProcess,' in init_content
    assert '    "React": ReactConfig,' in init_content


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

            from chemunited_workflow import (
                NodeExecutionContext,
                Process,
                WorkflowEdgeSpec,
                WorkflowNodeSpec,
            )


            class ProcessConfig(BaseModel):
                model_config = ConfigDict(frozen=True)


            class CustomProcess(Process[ProcessConfig]):
                \"\"\"User-defined workflow process.\"\"\"

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
    assert "def fresh_step(self, ctx: NodeExecutionContext) -> bool:" in updated
    assert 'ctx.runtime.status_message = "Fresh Step ran."' in updated
    assert "def _prepare_stock(self) -> str:" in updated


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


def test_sync_process_writes_node_label_and_description(tmp_path):
    session = ProjectSession()
    session.new(name="demo", location=tmp_path, init_git=False)
    working_dir = tmp_path / "demo"

    workflow = ProcessWorkflow("React")
    workflow.add_block(
        node_id="script_1",
        method="script_1",
        label="Prepare sample",
        description="Mix the starting materials",
        position=(100.0, 200.0),
    )

    assert session.sync_process("React", workflow) is True

    source = (working_dir / "protocols" / "React.py").read_text(encoding="utf-8")
    assert (
        "from chemunited_quantities import "
        "ChemQuantityValidator, ChemUnitQuantity"
    ) in source
    assert "node_id='script_1'," in source
    assert "method='script_1'," in source
    assert "label='Prepare sample'," in source
    assert "description='Mix the starting materials'," in source
    assert "position=(100.0, 200.0)," in source


def test_sync_process_roundtrip_preserves_special_block_types_and_loopback(tmp_path):
    session = ProjectSession()
    session.new(name="demo", location=tmp_path, init_git=False)

    workflow = ProcessWorkflow("React")
    workflow.add_block(
        node_id="conditional_1",
        method="conditional_1",
        position=(100.0, 0.0),
        block_tag=ProtocolBlock.IF,
    )
    workflow.add_block(
        node_id="script_1",
        method="script_1",
        position=(220.0, 0.0),
    )
    workflow.add_block(
        node_id="loop_1",
        method="loop_1",
        position=(340.0, 0.0),
        block_tag=ProtocolBlock.LOOP,
    )
    workflow.add_connection("start", "conditional_1")
    workflow.add_connection(
        "conditional_1",
        "script_1",
        start_role="top",
        condition=False,
        inflection_points=[(180.0, 40.0), (220.0, 40.0)],
    )
    workflow.add_connection(
        "conditional_1",
        "end",
        start_role="bottom",
        condition=True,
    )
    workflow.add_connection("script_1", "loop_1")
    workflow.add_connection("loop_1", "end")
    workflow.add_connection(
        "loop_1",
        "script_1",
        start_role="bottom",
        loopback=True,
        trigger_on=False,
        inflection_points=[(300.0, -20.0)],
    )

    synced = session.sync_process("React", workflow)

    assert synced is True
    content = (tmp_path / "demo" / "protocols" / "React.py").read_text(encoding="utf-8")
    assert "block_tag='if'" in content
    assert "block_tag='loop'" in content
    assert "inflection_points=[(180.0, 40.0), (220.0, 40.0)]" in content
    assert "inflection_points=[(300.0, -20.0)]" in content

    restored_classes = session.load_process_classes()
    restored = OrchestratorProjectFile._workflow_from_process_class(
        "React",
        restored_classes["React"],
    )

    assert restored.get_block("conditional_1").block_tag == ProtocolBlock.IF
    assert restored.get_block("loop_1").block_tag == ProtocolBlock.LOOP
    conditional_false = restored.get_connection("conditional_1", "script_1")
    assert conditional_false is not None
    assert conditional_false.start_role == "top"
    assert conditional_false.inflection_points == [(180.0, 40.0), (220.0, 40.0)]
    loopback = restored.get_connection("loop_1", "script_1")
    assert loopback is not None
    assert loopback.loopback is True
    assert loopback.start_role == "bottom"
    assert loopback.inflection_points == [(300.0, -20.0)]


def test_restore_workflow_infers_legacy_block_types_when_not_explicitly_saved(tmp_path):
    session = ProjectSession()
    session.new(name="demo", location=tmp_path, init_git=False)
    session.save_process(
        "React",
        dedent(
            """
            from __future__ import annotations

            import networkx as nx
            from pydantic import BaseModel, ConfigDict

            from chemunited_workflow import (
                NodeExecutionContext,
                Process,
                WorkflowEdgeSpec,
                WorkflowNodeSpec,
            )


            class ProcessConfig(BaseModel):
                model_config = ConfigDict(frozen=True)


            class CustomProcess(Process[ProcessConfig]):
                \"\"\"User-defined workflow process.\"\"\"

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
                        "conditional_1",
                        **WorkflowNodeSpec(
                            node_id="conditional_1",
                            method="conditional_1",
                            position=(100.0, 0.0),
                        ).model_dump(exclude_none=True),
                    )

                    graph.add_node(
                        "script_1",
                        **WorkflowNodeSpec(
                            node_id="script_1",
                            method="script_1",
                            position=(200.0, 0.0),
                        ).model_dump(exclude_none=True),
                    )

                    graph.add_node(
                        "loop_1",
                        **WorkflowNodeSpec(
                            node_id="loop_1",
                            method="loop_1",
                            position=(300.0, 0.0),
                        ).model_dump(exclude_none=True),
                    )

                    graph.add_node(
                        "end",
                        **WorkflowNodeSpec(
                            node_id="end",
                            method="finish",
                            position=(400.0, 0.0),
                        ).model_dump(exclude_none=True),
                    )

                    graph.add_edge(
                        "start",
                        "conditional_1",
                        **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
                    )

                    graph.add_edge(
                        "conditional_1",
                        "script_1",
                        **WorkflowEdgeSpec(condition=False).model_dump(exclude_none=True),
                    )

                    graph.add_edge(
                        "conditional_1",
                        "end",
                        **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
                    )

                    graph.add_edge(
                        "script_1",
                        "loop_1",
                        **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
                    )

                    graph.add_edge(
                        "loop_1",
                        "end",
                        **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
                    )

                    graph.add_edge(
                        "loop_1",
                        "script_1",
                        loopback=True,
                        trigger_on=False,
                    )

                    return graph

                def start(self, ctx: NodeExecutionContext) -> bool:
                    return True

                def conditional_1(self, ctx: NodeExecutionContext) -> bool:
                    return True

                def script_1(self, ctx: NodeExecutionContext) -> bool:
                    return True

                def loop_1(self, ctx: NodeExecutionContext) -> bool:
                    return True

                def finish(self, ctx: NodeExecutionContext) -> bool:
                    return True
            """
        ).strip()
        + "\n",
    )

    restored_classes = session.load_process_classes()
    restored = OrchestratorProjectFile._workflow_from_process_class(
        "React",
        restored_classes["React"],
    )

    assert restored.get_block("conditional_1").block_tag == ProtocolBlock.IF
    assert restored.get_block("loop_1").block_tag == ProtocolBlock.LOOP
    loopback = restored.get_connection("loop_1", "script_1")
    assert loopback is not None
    assert loopback.loopback is True
    assert loopback.start_role == "bottom"
