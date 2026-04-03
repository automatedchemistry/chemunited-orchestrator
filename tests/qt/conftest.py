import datetime
from pathlib import Path

import pytest
from PyQt5.QtGui import QPixmap
from pytestqt.qtbot import QtBot

SCREENSHOT_DIR = Path("tests/screenshots")


def _capture(widget, name: str, test_name: str) -> None:
    folder = SCREENSHOT_DIR / test_name
    folder.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%H%M%S_%f")
    path = folder / f"{name}_{ts}.png"
    pixmap = QPixmap(widget.size())
    widget.render(pixmap)
    pixmap.save(str(path), "PNG")
    print(f"[screenshot] {path}")


@pytest.fixture
def screenshot(request):
    test_name = request.node.name

    def take(widget, label: str = "snap") -> None:
        _capture(widget, label, test_name)

    return take


@pytest.fixture(autouse=True)
def screenshot_on_failure(request, qtbot: QtBot):
    yield
    rep = getattr(request.node, "rep_call", None)
    if rep is not None and rep.failed:
        for i, widget in enumerate(qtbot.widgets):
            _capture(widget, f"FAILED_widget_{i}", request.node.name)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, "rep_" + rep.when, rep)
