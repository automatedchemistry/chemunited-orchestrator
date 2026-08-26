from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, cast

from PyQt5.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QApplication


class QtMainThreadBridge(QObject):
    _call_requested = pyqtSignal(object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._call_requested.connect(  # type: ignore[call-arg]
            self._run_call,
            Qt.QueuedConnection,  # type: ignore[attr-defined]
        )

    def call(self, func: Callable[[], Any], *, timeout: float = 30.0) -> Any:
        app = QApplication.instance()
        if app is None or QThread.currentThread() == app.thread():
            return func()

        done = threading.Event()
        state: dict[str, Any] = {}
        self._call_requested.emit((func, done, state))
        if not done.wait(timeout):
            raise TimeoutError("Timed out waiting for the Qt main thread.")
        if "error" in state:
            raise state["error"]
        return state.get("result")

    @pyqtSlot(object)
    def _run_call(self, payload: object) -> None:
        func, done, state = cast(
            tuple[Callable[[], Any], threading.Event, dict[str, Any]],
            payload,
        )
        try:
            state["result"] = func()
        except BaseException as exc:
            state["error"] = exc
        finally:
            done.set()
