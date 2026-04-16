from pathlib import Path

from chemunited.workflow.orchestrator import BaseParameters, Platform


class MainParameters(BaseParameters):
    """Main parameters for the process."""

    pass


MAIN_PARAMETERS = MainParameters()
PLATFORM = Platform.from_json(Path(__file__).parent / "connectivity.json")
