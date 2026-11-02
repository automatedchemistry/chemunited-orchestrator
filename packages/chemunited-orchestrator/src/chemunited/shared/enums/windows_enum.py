from enum import Enum, auto


class WindowCategory(Enum):
    SETUP = auto()
    SIMULATION = auto()


class SetupStepMode(Enum):
    NONE = auto()
    DESIGN = auto()
    DETAIL = auto()
    PROTOCOLS = auto()
    CONNECTIVITY = auto()
    PRE_RUN = auto()
