from enum import Enum, auto


class WindowCategory(Enum):
    SETUP = auto()
    SIMULATION = auto()
    EXECUTION = auto()


class SetupStepMode(Enum):
    NONE = auto()
    DESIGN = auto()
    DETAIL = auto()
    EXECUTION = auto()
    PROTOCOLS = auto()
    CONNECTIVITY = auto()
