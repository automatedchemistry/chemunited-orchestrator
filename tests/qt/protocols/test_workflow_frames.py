from pathlib import Path
from types import SimpleNamespace

from chemunited_core.protocols import CommandSignature
from chemunited_workflow.enums import NodeState
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from chemunited.connectivity.openapi_commands import merge_openapi_commands
from chemunited.elements.component.protocols.valves import (
    ThreePortTwoPositionValveProtocols,
)
from chemunited.protocols.workflows.controller import WorkflowController
from chemunited.protocols.workflows.process_workflow import ProcessWorkflow
from chemunited.protocols.workflows.workflow_frames import (
    COMMAND_BLOCK_GUIDANCE,
    LOOP_ITERATION_GUIDANCE,
    WorkflowGraph,
    _build_command_model,
    _validate_command_block,
)
from chemunited.shared.editor.protocols.command import CommandEditorDialog
from chemunited.shared.enums import WindowCategory
from chemunited.shared.enums.protocols_enum import ProtocolBlock


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
    command = (
        ThreePortTwoPositionValveProtocols("ValveA")
        .commands["position"]
        .model_validate(
            {
                "component": "ValveA",
                "command": "position",
                "method": "PUT",
                "wait_time": 1.25,
                "wait_feedback_status": True,
                "connect": "[[0, 1]]",
            }
        )
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
    command = (
        ThreePortTwoPositionValveProtocols("ValveA")
        .commands["position"]
        .model_validate(
            {
                "component": "ValveA",
                "command": "position",
                "method": "PUT",
                "wait_time": 0.0,
                "wait_feedback_status": False,
                "connect": "[[1, 2]]",
            }
        )
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


def test_command_editor_dialog_saves_node_metadata(qtbot: QtBot) -> None:
    command = CommandSignature(
        component="PumpA",
        command="infuse",
        method="PUT",
    )
    dialog = CommandEditorDialog(
        function_name="command_1",
        command_model=command,
        label="Infuse sample",
        description="Initial description",
    )
    qtbot.addWidget(dialog)
    captured = []
    dialog.metadata_saved.connect(lambda *values: captured.append(values))

    dialog.node_metadata_editor.set_values(
        "Dose reagent",
        "Add reagent to the reactor",
    )
    dialog._on_save()

    assert captured == [
        (
            "command_1",
            "Dose reagent",
            "Add reagent to the reactor",
        )
    ]


def test_workflow_node_displays_and_updates_metadata(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    workflow = ProcessWorkflow("React")
    workflow.add_block(
        node_id="script_1",
        method="script_1",
        label="Prepare sample",
        description="Mix the starting materials",
        position=(100.0, 100.0),
    )
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)
    node = graph._nodes["script_1"]

    assert node.title_item.toPlainText() == "Prepare sample (script_1)"
    assert node.subtitle_item.toPlainText() == "Module"
    assert node.description_item.toPlainText() == "Mix the starting materials"
    assert "Label: Prepare sample" in node.body.toolTip()
    assert "Node ID: script_1" in node.body.toolTip()

    graph.controller.update_block_metadata(
        "script_1",
        "",
        "Updated description",
    )

    assert node.title_item.toPlainText() == "script_1"
    assert node.description_item.toPlainText() == "Updated description"
    assert workflow.get_block("script_1").label == "script_1"


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


def test_script_editor_saves_metadata_for_focused_block(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    process_file = tmp_path / "protocols" / "React.py"
    process_file.parent.mkdir(parents=True, exist_ok=True)
    process_file.write_text(
        "def script_1():\n    return True\n",
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

    graph._script_editor.node_metadata_editor.set_values(
        "Prepare sample",
        "Mix the starting materials",
    )
    graph._script_editor.save()

    block = workflow.get_block("script_1")
    assert block is not None
    assert block.label == "Prepare sample"
    assert block.description == "Mix the starting materials"
    assert graph._nodes["script_1"].title_item.toPlainText() == (
        "Prepare sample (script_1)"
    )

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


def test_context_menu_actions_persist_complete_blocks(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    workflow = ProcessWorkflow("React")
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)
    menu = graph._build_add_menu(QPointF(120.0, 80.0))

    for action in menu.actions()[:3]:
        action.trigger()

    process_file = tmp_path / "protocols" / "React.py"
    source = process_file.read_text(encoding="utf-8")
    expected = {
        "script_1": ProtocolBlock.SCRIPT,
        "loop_1": ProtocolBlock.LOOP,
        "conditional_1": ProtocolBlock.IF,
    }
    for method_name, block_tag in expected.items():
        block = workflow.get_block(method_name)
        assert block is not None
        assert block.block_tag == block_tag
        assert block.ports_numbers == 1
        assert method_name in graph._nodes
        assert source.count(f"def {method_name}(") == 1
        assert source.count(f"node_id={method_name!r},") == 1


def test_context_menu_loop_creates_missing_process_file(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    workflow = ProcessWorkflow("React")
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)

    graph._build_add_menu(QPointF()).actions()[1].trigger()

    process_file = tmp_path / "protocols" / "React.py"
    source = process_file.read_text(encoding="utf-8")
    assert workflow.get_block("loop_1") is not None
    assert '"loop_1"' in source
    assert "def loop_1(self, ctx: NodeExecutionContext) -> bool:" in source
    for comment in LOOP_ITERATION_GUIDANCE:
        assert source.count(comment) == 1
    assert (tmp_path / "protocols" / "__init__.py").is_file()


def test_loop_iteration_guidance_survives_repeated_sync(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    workflow = ProcessWorkflow("React")
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)

    graph._build_add_menu(QPointF()).actions()[1].trigger()
    assert graph.sync_script() is True
    assert graph.sync_script() is True

    source = (tmp_path / "protocols" / "React.py").read_text(encoding="utf-8")
    for comment in LOOP_ITERATION_GUIDANCE:
        assert source.count(comment) == 1


def test_iteration_guidance_is_only_added_to_loop_blocks(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    workflow = ProcessWorkflow("React")
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)

    menu = graph._build_add_menu(QPointF())
    menu.actions()[0].trigger()
    menu.actions()[2].trigger()

    source = (tmp_path / "protocols" / "React.py").read_text(encoding="utf-8")
    for comment in LOOP_ITERATION_GUIDANCE:
        assert comment not in source


def test_removing_block_synchronizes_graph_and_method(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    workflow = ProcessWorkflow("React")
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)
    graph._build_add_menu(QPointF()).actions()[1].trigger()

    graph.controller.remove_block("loop_1")

    source = (tmp_path / "protocols" / "React.py").read_text(encoding="utf-8")
    assert workflow.get_block("loop_1") is None
    assert "loop_1" not in graph._nodes
    assert '"loop_1"' not in source
    assert "def loop_1(" not in source


def test_context_menu_add_rolls_back_when_process_file_is_invalid(
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch,
) -> None:
    process_file = tmp_path / "protocols" / "React.py"
    process_file.parent.mkdir(parents=True, exist_ok=True)
    original = "def broken(:\n    pass\n"
    process_file.write_text(original, encoding="utf-8")
    workflow = ProcessWorkflow("React")
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)
    errors: list[str] = []
    monkeypatch.setattr(graph, "_show_script_sync_error", errors.append)

    graph._build_add_menu(QPointF()).actions()[1].trigger()

    assert workflow.get_block("loop_1") is None
    assert "loop_1" not in graph._nodes
    assert process_file.read_text(encoding="utf-8") == original
    assert len(errors) == 1


def test_command_injection_is_skipped_when_block_persistence_fails(
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch,
) -> None:
    process_file = tmp_path / "protocols" / "React.py"
    process_file.parent.mkdir(parents=True, exist_ok=True)
    process_file.write_text("def broken(:\n", encoding="utf-8")
    workflow = ProcessWorkflow("React")
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)
    errors: list[str] = []
    injected: list[tuple[str, str]] = []
    monkeypatch.setattr(graph, "_show_script_sync_error", errors.append)
    monkeypatch.setattr(
        graph,
        "_inject_to_script",
        lambda method, content: injected.append((method, content)) or True,
    )

    added = graph._add_command_block(
        QPointF(),
        'self.platform["PumpA"].put("infuse")',
    )

    assert added is False
    assert workflow.get_block("command_1") is None
    assert injected == []
    assert len(errors) == 1


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
        self.platform["ValveA"].put("position", connect="[[1, 2]]")
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
    assert extras["Options"] == ["[[1, 2]]", "[[2, 3]]"]


def test_command_block_reconstruction_distinguishes_get_and_put_endpoints(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    from chemunited_core.protocols.technical import (
        HeiConnectTemperatureControlProtocols,
        SetTemperatureParameter,
    )

    protocol = HeiConnectTemperatureControlProtocols("pt100")
    components = {
        "pt100": SimpleNamespace(protocols=protocol),
    }
    workflow = ProcessWorkflow("React")
    graph = _make_graph(
        working_dir=tmp_path,
        workflow=workflow,
        qtbot=qtbot,
        components=components,
    )
    source = """
class CustomProcess:
    def command_1(self, ctx: NodeExecutionContext) -> bool:
        self.platform["pt100"].put("temperature", temp="10 degC")
        return True
"""

    command_class = graph._resolve_command_signature_class(
        "pt100",
        "temperature",
        "PUT",
    )
    command = _build_command_model(
        source,
        "command_1",
        "CustomProcess",
        sig_cls=command_class,
    )

    assert command_class is SetTemperatureParameter
    assert command is not None
    assert command.method == "PUT"
    assert command.temp.to("degC").magnitude == 10


def test_command_block_reconstruction_resolves_dynamic_openapi_command(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    from chemunited_core.protocols import ComponentProtocol

    protocol = ComponentProtocol("PumpA")
    merge_openapi_commands(
        protocol=protocol,
        openapi={
            "paths": {
                "/Pump/device/prime": {
                    "put": {
                        "parameters": [{"name": "volume", "in": "query"}],
                    }
                }
            }
        },
        device="Pump",
        component="device",
    )
    components = {
        "PumpA": SimpleNamespace(protocols=protocol),
    }
    workflow = ProcessWorkflow("React")
    graph = _make_graph(
        working_dir=tmp_path,
        workflow=workflow,
        qtbot=qtbot,
        components=components,
    )
    source = """
class CustomProcess:
    def command_1(self, ctx: NodeExecutionContext) -> bool:
        self.platform["PumpA"].put("prime", volume="1 ml")
        return True
"""

    command_class = graph._resolve_command_signature_class("PumpA", "prime", "PUT")
    command = _build_command_model(
        source,
        "command_1",
        "CustomProcess",
        sig_cls=command_class,
    )

    assert command_class is protocol.commands["prime"]
    assert command is not None
    assert command.command == "prime"
    assert command.method == "PUT"
    assert command.volume == "1 ml"


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
    graph._update_command_script("command_1", command)

    source = process_file.read_text(encoding="utf-8")
    assert 'self.platform["PumpA"].put(' in source
    assert '            "infuse",' in source
    assert "wait_feedback_status=True," in source
    assert source.count("\n        return True\n") == 1
    assert source.count(COMMAND_BLOCK_GUIDANCE) == 1
    assert source.index('self.platform["PumpA"].put(') < source.index(
        "\n        return True"
    )


def test_new_command_block_replaces_generated_status_stub(
    tmp_path: Path,
    qtbot: QtBot,
) -> None:
    workflow = ProcessWorkflow("React")
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)

    added = graph._add_command_block(
        QPointF(),
        'self.platform["PumpA"].put("infuse")',
    )

    assert added is True
    source = (tmp_path / "protocols" / "React.py").read_text(encoding="utf-8")
    assert 'ctx.runtime.status_message = "Command 1 ran."' not in source
    assert source.count(COMMAND_BLOCK_GUIDANCE) == 1
    assert 'self.platform["PumpA"].put("infuse")' in source
    assert source.index('self.platform["PumpA"].put("infuse")') < source.index(
        "\n        return True",
        source.index("def command_1"),
    )


def test_command_block_validation_accepts_comments_get_and_put() -> None:
    for command_call, expected_method in (
        ('self.platform["PumpA"].put("infuse", wait_time=0.0)', "PUT"),
        ('self.platform["PumpA"].get("status")', "GET"),
    ):
        source = f"""
class CustomProcess:
    def command_1(self, ctx):
        # User comments are safe here.
        {command_call}
        return True
"""

        parsed, error = _validate_command_block(
            source,
            "command_1",
            "CustomProcess",
        )

        assert error is None
        assert parsed is not None
        assert parsed[2] == expected_method


def test_command_block_validation_rejects_noncanonical_bodies() -> None:
    invalid_bodies = (
        (
            'ctx.runtime.status_message = "Running"\n'
            '        self.platform["PumpA"].put("infuse")\n'
            "        return True",
            "first executable statement",
        ),
        (
            '"Command docstring"\n'
            '        self.platform["PumpA"].put("infuse")\n'
            "        return True",
            "Docstrings are not allowed",
        ),
        (
            'self.platform["PumpA"].put("infuse")\n'
            '        self.platform["PumpA"].get("status")\n'
            "        return True",
            "exactly one platform call",
        ),
        ('self.platform["PumpA"].put("infuse")', "must end with `return True`"),
        (
            'self.platform[component].put("infuse")\n        return True',
            "literal component name",
        ),
        (
            'self.platform["PumpA"].post("infuse")\n        return True',
            ".get(...) or .put(...)",
        ),
    )

    for body, expected_reason in invalid_bodies:
        source = f"""
class CustomProcess:
    def command_1(self, ctx):
        {body}
"""
        parsed, error = _validate_command_block(
            source,
            "command_1",
            "CustomProcess",
        )

        assert parsed is None
        assert error is not None
        assert expected_reason in error.reason
        assert error.line >= 3


def test_invalid_command_block_shows_actionable_location(
    tmp_path: Path,
    qtbot: QtBot,
    monkeypatch,
) -> None:
    process_file = tmp_path / "protocols" / "React.py"
    process_file.parent.mkdir(parents=True, exist_ok=True)
    process_file.write_text(
        "class CustomProcess:\n"
        "    def command_1(self, ctx):\n"
        '        ctx.runtime.status_message = "Running"\n'
        '        self.platform["PumpA"].put("infuse")\n'
        "        return True\n",
        encoding="utf-8",
    )
    workflow = ProcessWorkflow("React")
    workflow.add_block(
        node_id="command_1",
        method="command_1",
        block_tag=ProtocolBlock.COMMAND,
    )
    graph = _make_graph(working_dir=tmp_path, workflow=workflow, qtbot=qtbot)
    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(
        graph,
        "_show_command_editor_error",
        lambda title, message: shown.append((title, message)),
    )

    graph._handle_node_double_click(graph._nodes["command_1"])

    assert len(shown) == 1
    title, message = shown[0]
    assert title == "Invalid command block"
    assert str(process_file.resolve()) in message
    assert "Line: 3" in message
    assert "first executable statement" in message
    assert "Expected format:" in message
    assert 'self.platform["component"].put("command", ...)' in message
