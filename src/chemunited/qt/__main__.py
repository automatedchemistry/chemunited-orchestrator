import sys
from pathlib import Path

import rich_click as click
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from chemunited.qt.setup import SetupWindow


@click.command()
@click.argument("project_file", type=click.Path(exists=True), required=False)
def main(project_file: str | None = None) -> None:
    """Entry point for launching the ChemUnited GUI."""
    if sys.platform == "win32":
        import ctypes

        # Set AppUserModelID to group app instances and use custom icon
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "org.chemunited.app"
        )

    # Set high DPI settings for better display scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough  # type: ignore[attr-defined]
    )
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)  # type: ignore[attr-defined]
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)  # type: ignore[attr-defined]

    app = QApplication(sys.argv)

    # Set application icon for all windows (including taskbar)
    app.setWindowIcon(QIcon(":/icons/icons/chemunited.svg"))

    window = SetupWindow()
    if project_file:
        window.orchestrator.open_project(Path(project_file).resolve())
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
