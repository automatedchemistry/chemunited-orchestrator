from pathlib import Path
from types import SimpleNamespace

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from chemunited.qt.protocols.workflows.controller import WorkflowController
from chemunited.qt.protocols.workflows.process_workflow import ProcessWorkflow
from chemunited.qt.protocols.workflows.workflow_frames import WorkflowGraph
from chemunited.qt.shared.enums import WindowCategory


class _WorkflowHost(QWidget):
    def __init__(self, working_dir: Path | None):
        super().__init__()
        self.orchestrator = SimpleNamespace(working_dir=working_dir)


def _make_graph(
    *,
    working_dir: Path,
    workflow: ProcessWorkflow,
    qtbot: QtBot,
) -> WorkflowGraph:
    host = _WorkflowHost(working_dir)
    graph = WorkflowGraph(
        parent=host,
        window_container=WindowCategory.SETUP,
        controller=WorkflowController(workflow=workflow),
    )
    qtbot.addWidget(host)
    qtbot.addWidget(graph)
    return graph


def test_double_click_opens_script_editor_for_valid_process_file(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    process_file = tmp_path / "protocols" / "React.py"
    process_file.parent.mkdir(parents=True, exist_ok=True)
    process_file.write_text(
        "from __future__ import annotations\n\n\ndef script_1():\n    return True\n",
        encoding="utf-8",
    )

    workflow = ProcessWorkflow("React")
    workflow.add_block(
        node_id="script_1",
        method="script_1",
        position=(100.0, 100.0),
    )
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)

    graph._handle_node_double_click(graph._nodes["script_1"])
    qtbot.wait(0)

    assert graph._script_editor is not None
    assert graph._script_editor.editor.path == process_file
    assert workflow.get_block("script_1").file_path == process_file

    graph._script_editor.close()


def test_mouse_double_click_event_opens_script_editor(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    process_file = tmp_path / "protocols" / "React.py"
    process_file.parent.mkdir(parents=True, exist_ok=True)
    process_file.write_text(
        "from __future__ import annotations\n\n\ndef script_1():\n    return True\n",
        encoding="utf-8",
    )

    workflow = ProcessWorkflow("React")
    workflow.add_block(
        node_id="script_1",
        method="script_1",
        position=(100.0, 100.0),
    )
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)
    graph.resize(900, 600)
    graph.show()
    qtbot.waitExposed(graph)

    node = graph._nodes["script_1"]
    scene_pos = node.sceneBoundingRect().center()
    view_pos = graph.mapFromScene(scene_pos)

    qtbot.mouseDClick(graph.viewport(), Qt.LeftButton, pos=view_pos)
    qtbot.wait(0)

    assert graph._script_editor is not None
    assert graph._script_editor.editor.path == process_file

    graph._script_editor.close()


def test_double_click_ignores_invalid_process_file(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    process_file = tmp_path / "protocols" / "React.py"
    process_file.parent.mkdir(parents=True, exist_ok=True)
    process_file.write_text("def broken(:\n    pass\n", encoding="utf-8")

    workflow = ProcessWorkflow("React")
    workflow.add_block(
        node_id="script_1",
        method="script_1",
        position=(100.0, 100.0),
    )
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)

    graph._handle_node_double_click(graph._nodes["script_1"])
    qtbot.wait(0)

    assert graph._script_editor is None
