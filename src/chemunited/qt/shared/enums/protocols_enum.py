from enum import Enum


class ProtocolBlock(str, Enum):
    SCRIPT = "script"
    START = "start"
    END = "end"
    LOOP = "loop"
    IF = "if"
