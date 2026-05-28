import json
from pathlib import Path

from loguru import logger as _logger

from chemunited.qt.shared.enums import WindowCategory

from .connectivity import OrchestratorConnectivity

logger = _logger.bind(window=WindowCategory.EXECUTION)


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

    def execute(self) -> bool:
        """
        Start or stop the execution of the protocol.
        Return True if the execution was started or keeping to run.
        Return False if the execution was stopped or failed to start.
        """
        if self.parent_ref.status_widget.text() == "Offline":
            logger.warning("No API running — connect first.")
            return False
        api_process = self.parent_ref.api_process
        if api_process is None:
            logger.warning("No API running — connect first.")
            return False

        status = api_process.client.get("status")
        if status.get("is_running"):
            # It is running, so the user want to stop the current execution.
            if not api_process.client.post("stop"):
                logger.error("Failed to stop the current execution.")
                return True  # Return True because the execution is still running.
            logger.info("Successfully stopped the current execution.")
            return False  # Return False because the execution was stopped.

        # It is not running, so the user want to start the current execution.

        event_source = api_process.client.get(
            endpoint="execute/stream",
            params={
                "protocol_hystoric_name": str(self.project_protocol_script_dir),
            },
        )
        if event_source is None:
            logger.error("Failed to start the current execution.")
            return False  # Return False because the execution was not started.

        return True
