from typing import TYPE_CHECKING, Any

from PyQt5.QtCore import QObject, Qt
from qfluentwidgets import InfoBar, InfoBarPosition

from chemunited.qt.elements.access import Components, Connections
from chemunited.qt.protocols.workflows import ProcessWorkflow
from chemunited.qt.shared.enums import WindowCategory
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

    def _build_infor_flyout(self, r: dict[str, Any]):
        message = r.get("message", "")
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
