import sys
from pathlib import Path

import rich_click as click
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

# Import WebEngine BEFORE any Qt widgets - required for Monaco Editor
try:
    import PyQt5.QtWebEngineWidgets  # noqa: F401
except ImportError:
    pass  # Will fail later with better error if Monaco is used

# Import theme system and initialize before creating QApplication
from chemunited.setup import SetupWindow

# Import Qt resources - must be done before using :/ paths
from chemunited.shared.resources import resources_rc  # noqa: F401
from chemunited.shared.widgets.app_theme import init_theme
from chemunited.shared.widgets.logo_window import show_waiting

# Initialize theme system (dark/light mode)
init_theme()

_APP_ID = "org.chemunited.orchestrator"
_ICON_PATH = ":/icons/icons/chemunited.ico"


@click.command()
@click.argument("project_file", type=click.Path(exists=True), required=False)
@click.option(
    "--overwrite",
    is_flag=True,
    default=False,
    help="Overwrite an existing project directory when importing a .chemunited file.",
)
def main(project_file: str | None = None, overwrite: bool = False) -> None:
    """Entry point for launching the ChemUnited GUI."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(_APP_ID)

    # Set high DPI settings for better display scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough  # type: ignore[attr-defined]
    )
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)  # type: ignore[attr-defined]
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)  # type: ignore[attr-defined]

    app = QApplication(sys.argv)

    app.setWindowIcon(QIcon(_ICON_PATH))

    show_waiting(3)

    window = SetupWindow()
    window.show()
    if project_file:
        _path = Path(project_file).resolve()
        _overwrite = overwrite
        QTimer.singleShot(
            0, lambda: window.orchestrator.open_project(_path, overwrite=_overwrite)
        )
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
