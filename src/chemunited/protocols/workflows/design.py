from enum import Enum

from qfluentwidgets import isDarkTheme


class NodeState(str, Enum):
    NOT_VISITED = "not_visited"
    WAITING = "waiting"
    RUNNING = "running"
    COMPLETED = "completed"
    INACTIVE = "inactive"
    FAILED = "failed"


NODE_COLORS_DARK = {
    NodeState.NOT_VISITED: "#9e9e9e",
    NodeState.WAITING: "#ff9800",
    NodeState.RUNNING: "#2196f3",
    NodeState.COMPLETED: "#4caf50",
    NodeState.INACTIVE: "#9e9e9e",
    NodeState.FAILED: "#f44336",
}

NODE_COLORS_LIGHT = {
    NodeState.NOT_VISITED: "#8c8c8c",  # Example: slightly different for light
    NodeState.WAITING: "#e68a00",
    NodeState.RUNNING: "#1e88e5",
    NodeState.COMPLETED: "#43a047",
    NodeState.INACTIVE: "#8c8c8c",
    NodeState.FAILED: "#e53935",
}


def get_node_color(state: NodeState) -> str:
    """Returns the correct HEX color for the node state depending on system theme."""
    if isDarkTheme():
        return NODE_COLORS_DARK.get(state, "#ffffff")
    else:
        return NODE_COLORS_LIGHT.get(state, "#000000")
