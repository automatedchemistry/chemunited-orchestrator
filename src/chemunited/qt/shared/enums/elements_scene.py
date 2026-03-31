from enum import Enum, auto


class ConnectionType(Enum):
    FLOW = auto()
    MOVEMENT = auto()
    HEAT = auto()
    ELECTRONIC = auto()
    