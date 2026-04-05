from typing import Optional, Any, Iterable
from loguru import logger
from .enums import WindowCategory
import queue


class LogQueue:
    def __init__(self):
        self.queues: dict[WindowCategory, queue.Queue] = {}

    def _q(self, window: WindowCategory) -> queue.Queue:
        return self.queues.setdefault(window, queue.Queue())

    def push(self, record: dict):
        window = record.get("extra", {}).get("window", WindowCategory.SETUP)
        self._q(window).put(record)

    def try_pop(self, window: WindowCategory = WindowCategory.SETUP):
        try:
            return self._q(window).get_nowait()
        except queue.Empty:
            return None


def setup_logging_once():
    global _sink_id
    if _sink_id is not None:
        return

    def sink(message):
        LOG_QUEUE.push(message.record)

    _sink_id = logger.add(sink, level="TRACE")  # type:ignore[assignment]


def remove_sink():
    if _sink_id is not None:
        logger.remove(_sink_id)


def logger_context(
    url: Optional[str] = None,
    kwargs: Optional[dict] = None,
    command: Optional[str] = None,
    component_id: Optional[str] = None,
    module_id: Optional[str] = None,
    suggested_action: Optional[str] = None,
    window: WindowCategory = WindowCategory.SETUP,
    duration: int = 4000,
    inspect_script: bool = False,
) -> dict[str, Any]:
    data = {
        "url": url,
        "kwargs": kwargs,
        "command": command,
        "component_id": component_id,
        "module_id": module_id,
        "suggested_action": suggested_action,
        "window": window,
        "duration": duration,
        "inspect_script": inspect_script,
    }
    return {k: v for k, v in data.items() if v is not None}


LOG_QUEUE = LogQueue()
_sink_id = None
setup_logging_once()


if __name__ == "__main__":

    def print_summary(r: dict) -> None:
        print("location :", f"{r['name']}:{r['function']}:{r['line']}")
        print("file     :", r["file"].name)
        print("level    :", r["level"].name, f"({r['level'].no})")
        print("message  :", r["message"])
        print("thread   :", r["thread"].name)
        print("process  :", r["process"].id)
        print("extra    :", r["extra"])
        print("exception:", r["exception"])
        print("----------\n")

    def demo_level(
        level_name: str, message: str, *, with_exception: bool = False
    ) -> None:
        """
        Logs at a specific level, then prints the captured record.
        """
        if with_exception:
            try:
                1 / 0
            except Exception:
                logger.opt(exception=True).log(level_name, message)
        else:
            logger.log(level_name, message)

    # ----------------------------
    # Examples
    # ----------------------------
    def show_all_levels():
        demo_level("TRACE", "Trace: very detailed")
        print_summary(LOG_QUEUE.try_pop())
        demo_level("DEBUG", "Debug: diagnostic")
        print_summary(LOG_QUEUE.try_pop())
        demo_level("INFO", "Info: general status")
        print_summary(LOG_QUEUE.try_pop())
        demo_level("SUCCESS", "Success: operation completed")
        print_summary(LOG_QUEUE.try_pop())
        demo_level("WARNING", "Warning: something looks off")
        print_summary(LOG_QUEUE.try_pop())
        demo_level("ERROR", "Error: operation failed")
        print_summary(LOG_QUEUE.try_pop())
        demo_level("CRITICAL", "Critical: severe failure")
        print_summary(LOG_QUEUE.try_pop())

        # Example with exception info attached to the record
        demo_level("ERROR", "Error with exception=True", with_exception=True)
        print_summary(LOG_QUEUE.try_pop())

        logger.bind(run_id="RUN-123", component_id="Pump1", task_id="T42").info(
            "Bound extras example"
        )
        print_summary(LOG_QUEUE.try_pop())

        print(LOG_QUEUE.queues)

    setup_logging_once()
    show_all_levels()
    remove_sink()
