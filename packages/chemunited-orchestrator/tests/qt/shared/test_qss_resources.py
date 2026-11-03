from pathlib import Path

import pytest
from PyQt5.QtCore import QFile, QIODevice, QTextStream
from pytestqt.qtbot import QtBot

import chemunited.shared.resources as resources
from chemunited.shared.resources import resources_rc  # noqa: F401

QSS_DIR = Path(resources.__file__).parent / "qss"


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("name", ["main_window.qss", "loggings_widget.qss"])
def test_compiled_qss_matches_source(qtbot: QtBot, theme: str, name: str):
    """resources_rc.py must be rebuilt (pyrcc5) whenever a .qss file changes."""
    file = QFile(f":/styles/qss/{theme}/{name}")
    assert file.open(QIODevice.ReadOnly | QIODevice.Text)  # type: ignore[attr-defined]
    compiled = QTextStream(file).readAll()
    file.close()

    source = (QSS_DIR / theme / name).read_text(encoding="utf-8")

    assert compiled.replace("\r\n", "\n") == source.replace("\r\n", "\n")
