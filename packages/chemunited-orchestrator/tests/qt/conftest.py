import pytest


@pytest.fixture(autouse=True)
def _no_version_check(monkeypatch):
    """Never let SetupWindow's background update check actually run in tests.

    SetupWindow.initWindow() schedules _start_version_check() ~1s after
    construction, which starts a VersionCheckThread that makes real HTTPS
    calls to pypi.org (up to 5s timeout x 5 packages) with no shutdown
    coordination anywhere - closeEvent never stopped or waited for it. Any
    test whose window lives past that 1s mark can get torn down while the
    thread is still blocked on network I/O; Qt's parent/child cascade then
    destroys the still-running QThread and aborts the whole process
    ("QThread: Destroyed while thread is still running") - this is what was
    crashing full-suite runs, especially in CI where pypi.org is typically
    unreachable and every request stalls to its full timeout. SetupWindow.
    closeEvent now stops+waits for it too (belt and suspenders), but tests
    still shouldn't be making real network calls regardless.
    """
    monkeypatch.setattr(
        "chemunited.setup.SetupWindow._start_version_check", lambda self: None
    )


@pytest.fixture(autouse=True)
def _drain_deferred_deletes(qtbot):
    """Let deleteLater()'d widgets actually get destroyed before the next test.

    pytest-qt's own teardown (_close_widgets) calls widget.close() +
    deleteLater(), then a single bare QApplication.processEvents(). That one
    call is not reliably enough to fully process QEvent::DeferredDelete
    before the next test's fixtures start building a new window on top of
    the still-half-torn-down one - without this, the suite segfaults
    deterministically on this machine. qtbot.wait() drives a real event loop
    for a bit longer, giving deferred deletes a real chance to finish.
    """
    yield
    qtbot.wait(200)
