"""Resource-access helpers for the shared elements layer.

Provides path resolution for component figures so that callers never
need to hard-code directory structures or naming conventions.
"""
import os

# Absolute path to the bundled components image directory.
_COMPONENTS_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "resources", "components")
)


def get_svg_path(figure: str) -> str:
    """Return the file-system path to an SVG asset for *figure*.

    Looks for ``<figure>.svg`` (plain), ``<figure>DARK.svg``, or
    ``<figure>LIGHT.svg`` inside the bundled components directory.
    Returns an empty string when no SVG is found — callers should fall
    back to a plain QGraphicsRectItem in that case.

    Args:
        figure: The figure class name as stored in ComponentData.figure
                (e.g. ``"SyringePump"``).

    Returns:
        Absolute path string if an SVG file exists, otherwise ``""``.
    """
    if not figure:
        return ""
    for candidate in (f"{figure}.svg", f"{figure}DARK.svg", f"{figure}LIGHT.svg"):
        path = os.path.join(_COMPONENTS_DIR, candidate)
        if os.path.isfile(path):
            return os.path.normpath(path)
    return ""
