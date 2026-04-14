from chemunited.workflow.orchestrator import BaseParameters, Platform
from pathlib import Path


class MainParameters(BaseParameters):
    """Main parameters for the process."""
    pass


MAIN_PARAMETERS = MainParameters()
PLATFORM = Platform.from_json(Path(__file__).parent / "connectivity.json")