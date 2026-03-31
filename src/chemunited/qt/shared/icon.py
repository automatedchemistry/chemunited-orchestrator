from enum import Enum

from PyQt5.QtCore import QFile
from qfluentwidgets import FluentIconBase, Theme, isDarkTheme


def getIconColor():  # Assuming you have this function defined elsewhere
    if isDarkTheme():
        return "white"
    return "black"


class OrchestratorIcon(FluentIconBase, Enum):
    """Fluent icon"""

    ADD_FOLDER = "add_folder"
    AIR = "air"
    BOOLEAN = "boolean"
    BUILD = "build"
    CHEMICAL = "chemical"
    CHEMUNITED = "chemunited"
    CHEMUNITED_SIMU = "chemunited_simu"
    CHOICES = "choices"
    COLOR_SELECT = "color_select"
    COMPLETE = "complete"
    COMPONENT_ICON = "component_icon"
    IF = "block_if"
    CONNECTION = "connection"
    CSV = "csv"
    DATABASE = "database"
    DEVICE_HIERARCHY = "device_hierarchy"
    HOME = "home"
    INSPECT = "inspect"
    INTEGER = "integer"
    JSON = "json"
    LIST = "list"
    LOG = "log"
    LOOP = "block_for"
    MANUAL = "manual"
    MEASURE = "measure"
    MODULE = "module"
    MOVE = "move"
    ORCHESTRATOR = "orchestrator"
    OPEN_FOLDER = "open_folder"
    PAUSE = "pause"
    PLAY = "play"
    PRESSURE_LINE = "line_pressure"
    PROCESS = "process"
    PYTHON = "python"
    SELECT = "select"
    SCISSOR = "scissor"
    SIMULATION = "simulation"
    SLOW = "slow"
    SPEED = "speed"
    STOP = "stop"
    STRING = "string"
    TRASH = "trash"
    TOML = "toml"
    UPLOAD = "upload"
    VARIABLE = "variable"
    WAITING_ICON = "waiting_icon"
    WATER = "water"

    def path(self, theme=Theme.AUTO):
        resource_path = f":/icons/icons/{self.value}_{getIconColor()}.svg"
        if QFile.exists(resource_path):
            return resource_path
        else:
            # The icon has not theme-switch
            return f":/icons/icons/{self.value}.svg"
