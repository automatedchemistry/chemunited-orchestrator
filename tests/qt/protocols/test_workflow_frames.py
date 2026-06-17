from pathlib import Path
from types import SimpleNamespace

from chemunited.elements.component.protocols.valves import (
    ThreePortTwoPositionValveProtocols,
)
from chemunited_core.protocols import CommandSignature
from chemunited_workflow.enums import NodeState
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from chemunited.protocols.workflows.controller import WorkflowController
from chemunited.protocols.workflows.process_workflow import ProcessWorkflow
from chemunited.protocols.workflows.workflow_frames import (
    WorkflowGraph,
    _build_command_model,
)
from chemunited.shared.editor.protocols.command import CommandEditorDialog
from chemunited.shared.enums import WindowCategory


class _WorkflowHost(QWidget):
    def __init__(self, working_dir: Path | None, components=None):
        super().__init__()
        self.orchestrator = SimpleNamespace(
            working_dir=working_dir,
            components=components or {},
        )


def _make_graph(
    *,
    working_dir: Path,
    workflow: ProcessWorkflow,
    qtbot: QtBot,
    components=None,
) -> WorkflowGraph:
    host = _WorkflowHost(working_dir, components=components)
    graph = WorkflowGraph(
        parent=host,
        window_container=WindowCategory.SETUP,
        controller=WorkflowController(workflow=workflow),
    )
    qtbot.addWidget(host)
    qtbot.addWidget(graph)
    return graph


def test_workflow_graph_sets_node_status_and_clears_progress(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    workflow = ProcessWorkflow("React")
    workflow.add_block(
        node_id="script_1",
        method="script_1",
        position=(100.0, 100.0),
    )
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)
    node = graph._nodes["script_1"]

    graph.set_node_status("script_1", NodeState.RUNNING)

    assert node.progress_proxy is not None
    assert node.progress_bar is not None
    assert node.progress_proxy.isVisible()
    assert node.progress_bar._state == NodeState.RUNNING
    assert node.progress_bar.is_running()

    graph.set_node_status("script_1", NodeState.COMPLETED)
    assert node.progress_proxy.isVisible()
    assert node.progress_bar._state == NodeState.COMPLETED
    assert node.progress_bar.value() == 100
    assert not node.progress_bar.is_running()

    graph.set_node_status("script_1", NodeState.FAILED)
    assert node.progress_proxy.isVisible()
    assert node.progress_bar._state == NodeState.FAILED
    assert node.progress_bar.value() == 100

    graph.set_node_status("missing", NodeState.RUNNING)

    graph.set_node_status("script_1", NodeState.NOT_VISITED)
    assert not node.progress_proxy.isVisible()
    assert node.progress_bar._state == NodeState.NOT_VISITED

    graph.set_node_status("script_1", NodeState.RUNNING)
    assert node.progress_proxy.isVisible()
    assert node.progress_bar._state == NodeState.RUNNING

    graph.clear_progress()
    assert not node.progress_proxy.isVisible()
    assert node.progress_bar._state == NodeState.NOT_VISITED


def test_command_editor_dialog_is_form_only(qtbot: QtBot) -> None:
    command = ThreePortTwoPositionValveProtocols("ValveA").commands[
        "position"
    ].model_validate(
        {
            "component": "ValveA",
            "command": "position",
            "method": "PUT",
            "wait_time": 1.25,
            "wait_feedback_status": True,
            "connect": "[[0, 1]]",
        }
    )
    dialog = CommandEditorDialog(
        function_name="command_1",
        command_model=command,
    )
    qtbot.addWidget(dialog)

    cards = dialog._editor._cards

    assert not hasattr(dialog, "convert_to_script")
    assert not hasattr(dialog, "_convert_button")
    assert not hasattr(dialog, "_code_preview_widget")
    assert "wait_time" in cards
    assert "wait_feedback_status" in cards
    assert not cards["wait_time"].isHidden()
    assert not cards["wait_feedback_status"].isHidden()
    assert cards["component"].isHidden()
    assert cards["command"].isHidden()
    assert cards["method"].isHidden()


def test_command_editor_dialog_saves_execution_fields(qtbot: QtBot) -> None:
    command = ThreePortTwoPositionValveProtocols("ValveA").commands[
        "position"
    ].model_validate(
        {
            "component": "ValveA",
            "command": "position",
            "method": "PUT",
            "wait_time": 0.0,
            "wait_feedback_status": False,
            "connect": "[[0, 1]]",
        }
    )
    dialog = CommandEditorDialog(
        function_name="command_1",
        command_model=command,
    )
    qtbot.addWidget(dialog)
    captured = []
    dialog.saved.connect(captured.append)

    dialog._editor._cards["wait_time"].set_value(2.5)
    dialog._editor._cards["wait_feedback_status"].set_value(True)
    dialog._on_save()

    assert len(captured) == 1
    result = captured[0]
    assert result.wait_time == 2.5
    assert result.wait_feedback_status is True
    assert result.component == "ValveA"
    assert result.command == "position"


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


def test_command_block_reconstruction_uses_component_protocol_metadata(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    protocol = ThreePortTwoPositionValveProtocols("ValveA")
    components = {
        "ValveA": SimpleNamespace(protocols=protocol),
    }
    workflow = ProcessWorkflow("React")
    graph = _make_graph(
        working_dir=tmp_path,
        workflow=workflow,
        qtbot=qtbot,
        components=components,
    )

    command_class = graph._resolve_command_signature_class("ValveA", "position")

    assert command_class is protocol.commands["position"]

    source = """
class CustomProcess:
    def command_1(self, ctx: NodeExecutionContext) -> bool:
        platform["ValveA"].put("position", connect="[[0, 1]]")
        return True
"""
    command = _build_command_model(
        source,
        "command_1",
        "CustomProcess",
        sig_cls=command_class,
    )

    assert command is not None
    extras = type(command).model_fields["connect"].json_schema_extra or {}
    assert extras["Options"] == ["[[0, 1]]", "[[0, 2]]"]


def test_update_command_script_formats_saved_protocol(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    process_file = tmp_path / "protocols" / "React.py"
    process_file.parent.mkdir(parents=True, exist_ok=True)
    process_file.write_text(
        (
            "class CustomProcess:\n"
            "    def command_1(self, ctx):\n"
            "        self.platform['PumpA'].put('old')\n"
            "        return True\n"
        ),
        encoding="utf-8",
    )
    workflow = ProcessWorkflow("React")
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)
    command = CommandSignature(
        component="PumpA",
        command="infuse",
        method="PUT",
        wait_time=1.5,
        wait_feedback_status=True,
    )

    graph._update_command_script("command_1", command)

    source = process_file.read_text(encoding="utf-8")
    assert 'self.platform["PumpA"].put(' in source
    assert '            "infuse",' in source
    assert "wait_feedback_status=True," in source
