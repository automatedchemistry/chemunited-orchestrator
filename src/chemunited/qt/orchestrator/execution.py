import json
from pathlib import Path

from .connectivity import OrchestratorConnectivity


class OrchestratorExecution(OrchestratorConnectivity):

    def __init__(self, parent):
        super().__init__(parent)
        self.project_protocol_script_dir: Path | None = None

    def set_project_protocol_script_dir(self, dir: Path) -> None:
        self.project_protocol_script_dir = dir
        with open(self.project_protocol_script_dir, "r") as f:
            data = json.load(f)

        actual_process: str = ""
        for key, value in data.items():
            if key != "main_parameter":
                if hasattr(self.parent_ref.protocols_widget, "activate_process"):
                    process_name = key.split("Process")[0]
                    self.parent_ref.protocols_widget.activate_process(process_name)
                    if not actual_process:
                        actual_process = process_name
                        self.select_process(actual_process)
