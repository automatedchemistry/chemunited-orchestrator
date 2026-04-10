"""Quick visual test — run this file directly to try both editor windows.

    python -m chemunited.qt.elements.component.widgets.command_editor.example
or
    python src/chemunited/qt/elements/component/widgets/command_editor/example.py
"""

from __future__ import annotations

import sys

from PyQt5.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

from chemunited.qt.elements.component.protocols.pumps import WithdrawParameter
from chemunited.qt.elements.component.widgets.command_editor import (
    CommandEditorDialog,
    ScriptEditorDialog,
)


def open_command_editor(app: QApplication) -> None:
    # Build a pre-populated instance (component injected here as it would be
    # at runtime when the user double-clicks the block on the canvas).
    instance = WithdrawParameter(component="Pump")

    dlg = CommandEditorDialog(
        command_class=WithdrawParameter,
        instance=instance,
    )

    # When the user confirms "convert to script", close the command editor
    # and open the script editor with the pre-filled source.
    def _on_convert(source: str) -> None:
        script_dlg = ScriptEditorDialog(
            block_name="withdraw",
            source=source,
            converted_from_command=True,
        )
        script_dlg.saved.connect(lambda src: print("Script saved:\n", src))
        script_dlg.exec_()

    dlg.convert_to_script.connect(_on_convert)
    dlg.saved.connect(lambda inst: print("Command saved:", inst))
    dlg.exec_()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    setTheme(Theme.LIGHT)
    open_command_editor(app)
    sys.exit(0)
