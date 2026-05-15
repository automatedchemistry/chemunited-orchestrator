import json
from pathlib import Path

from .connectivity import OrchestratorConnectivity


def _process_name_from_protocol_key(key: str) -> str | None:
    process_name, separator, process_index = key.rpartition("_")
    if not separator or not process_name or not process_index.isdecimal():
        return None
    return process_name


class OrchestratorExecution(OrchestratorConnectivity):

    def __init__(self, parent):
        super().__init__(parent)
        self.project_protocol_script_dir: Path | None = None

    def set_project_protocol_script_dir(self, dir: Path) -> None:
        self.project_protocol_script_dir = dir
        with open(self.project_protocol_script_dir, "r", encoding="utf-8") as f:
            data = json.load(f)

        actual_process: str = ""
        for key in data:
            if key == "main_parameter":
                continue
            process_name = _process_name_from_protocol_key(key)
            if process_name is None:
                continue
            if hasattr(self.parent_ref.protocols_widget, "activate_process"):
                self.parent_ref.protocols_widget.activate_process(process_name)
                if not actual_process:
                    actual_process = process_name
                    self.select_process(actual_process)
