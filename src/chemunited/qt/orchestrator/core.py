from typing import TYPE_CHECKING, Any

from PyQt5.QtCore import QObject, Qt
from qfluentwidgets import InfoBar, InfoBarPosition

from chemunited.qt.elements.access import Components, Connections
from chemunited.qt.protocols.workflows import ProcessWorkflow
from chemunited.qt.shared.enums import SetupStepMode, WindowCategory
from chemunited.qt.shared.logger_queue import LOG_QUEUE

if TYPE_CHECKING:
    from chemunited.qt.setup import SetupWindow


class OrchestratorCore(QObject):

    MAX_LOG_RECORDS_PER_TICK = 256

    def __init__(self, parent: "SetupWindow"):
        super().__init__(parent)
        self.parent_ref = parent

        # Components used in the platform (devices and utensils)
        self.components: Components = Components()

        # Connections used in the platform (hydraulic, heat, electronic, movement)
        self.connections: Connections = Connections()

        # Protocols used in the platform
        self.protocols: dict[str, ProcessWorkflow] = {}

        # Attributes of the catch logs of report of the application

        self.parent_ref.drain_bus_timer.timeout.connect(self.verify_logs_queue)

        self.parent_ref.drain_bus_timer.start(500)

        self.last_log: str = ""

        self.exposed_logs_class: WindowCategory = WindowCategory.SETUP

    # Basic notifications - Gui inspect reports

    @staticmethod
    def _format_infor_flyout_content(r: dict[str, Any]) -> str:
        message = str(r.get("message", "") or "")
        exc = r.get("exception")
        if exc is None:
            return message

        exc_type_obj = getattr(exc, "type", None)
        exc_type = exc_type_obj.__name__ if exc_type_obj is not None else "Exception"
        exc_value = str(getattr(exc, "value", "") or "").strip()
        summary = exc_type if not exc_value else f"{exc_type}: {exc_value}"
        if summary and summary not in message:
            return f"{message}\n{summary}\nSee Detailed Records for traceback."
        return f"{message}\nSee Detailed Records for traceback."

    def _build_infor_flyout(self, r: dict[str, Any]):
        message = self._format_infor_flyout_content(r)
        self.last_log = message
        level = str(r.get("level").name).lower()  # type:ignore[union-attr]
        duration = r.get("extra", {}).get("duration", 4000)

        if level == "success":
            show_info = InfoBar.success
            position = InfoBarPosition.TOP
        elif level == "warning":
            show_info = InfoBar.warning
            position = InfoBarPosition.TOP
        elif level in {"error", "critical"}:
            show_info = InfoBar.error
            position = InfoBarPosition.BOTTOM_RIGHT
        else:
            return

        show_info(
            title=level,
            content=message,
            orient=Qt.Horizontal,  # type: ignore[attr-defined]
            isClosable=True,
            position=position,
            duration=duration,  # won't disappear automatically if it is -1
            parent=self.parent_ref,
        )

    def _additional_behaviours_logg(self, r): ...

    def verify_logs_queue(self):
        """Drain pending logs produced by worker threads.

        The queue is drained in bounded batches to avoid long UI stalls when the
        producer rate is high. Remaining events are handled in the next timer tick.
        """
        for _ in range(self.MAX_LOG_RECORDS_PER_TICK):
            r = LOG_QUEUE.try_pop(window=self.exposed_logs_class)
            if r is None:
                return
            if self.last_log == r.get("message", ""):
                # Repetitive message (adjacent duplicate).
                continue
            self._build_infor_flyout(r)
            self._additional_behaviours_logg(r)
            self.parent_ref.FrameLoggings.append_record(r)

    def switch_to_step(self, step: SetupStepMode) -> None:
        for component in self.components.values():
            component.graph.set_frame_mode(step)
        for connection in self.connections.values():
            connection.set_frame_mode(step)
        if step == SetupStepMode.PRE_RUN:
            self.parent_ref.preRunFrame.sync()
