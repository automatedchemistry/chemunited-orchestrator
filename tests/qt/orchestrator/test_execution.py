from __future__ import annotations

import json
from types import SimpleNamespace

from chemunited.qt.orchestrator.execution import (
    OrchestratorExecution,
    _process_name_from_protocol_key,
)


def test_process_name_from_protocol_key_uses_file_stem() -> None:
    assert _process_name_from_protocol_key("clean_0") == "clean"
    assert _process_name_from_protocol_key("my_process_12") == "my_process"
    assert _process_name_from_protocol_key("ReactProcess_1") == "ReactProcess"
    assert _process_name_from_protocol_key("main_parameter") is None
    assert _process_name_from_protocol_key("ReactProcess") is None
    assert _process_name_from_protocol_key("React_x") is None


def test_set_project_protocol_script_dir_activates_saved_process_names(
    tmp_path,
) -> None:
    path = tmp_path / "protocol.json"
    path.write_text(
        json.dumps(
            {
                "main_parameter": {},
                "clean_0": {},
                "ReactProcess_1": {},
                "my_process_2": {},
                "malformed": {},
            }
        ),
        encoding="utf-8",
    )

    class ProtocolsWidget:
        def __init__(self) -> None:
            self.activated: list[str] = []

        def activate_process(self, process_name: str) -> None:
            self.activated.append(process_name)

    protocols_widget = ProtocolsWidget()
    selected: list[str] = []
    execution = OrchestratorExecution.__new__(OrchestratorExecution)
    execution.parent_ref = SimpleNamespace(protocols_widget=protocols_widget)
    execution.select_process = selected.append

    execution.set_project_protocol_script_dir(path)

    assert protocols_widget.activated == ["clean", "ReactProcess", "my_process"]
    assert selected == ["clean"]
