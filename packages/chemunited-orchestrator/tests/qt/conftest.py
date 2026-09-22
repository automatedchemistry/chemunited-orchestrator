import pytest


@pytest.fixture(autouse=True)
def _drain_deferred_deletes(qtbot):
    """Let deleteLater()'d widgets actually get destroyed before the next test.

    pytest-qt's own teardown (_close_widgets) calls widget.close() +
    deleteLater(), then a single bare QApplication.processEvents(). That one
    call isn't reliably enough to process QEvent::DeferredDelete for windows
    that own a QMainWindow child (e.g. SetupWindow -> SimulateWindowReport),
    so those windows - and everything under them, including matplotlib
    Figures - stay alive and accumulate across the run instead of being
    freed. qtbot.wait() drives a real event loop long enough to drain them.
    """
    yield
    qtbot.wait(50)
