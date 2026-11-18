"""Run-scoped host for background graph nodes and ordered finite commands."""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import Future, wait
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable

from .command_events import current_node, set_current_node
from .exceptions import RunCancelledError

STOP_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class CommandOrigin:
    process: str | None = None
    node: str | None = None
    iteration: int | None = None


_origin: ContextVar[CommandOrigin | None] = ContextVar("command_origin", default=None)


def current_command_origin() -> CommandOrigin:
    return _origin.get() or CommandOrigin(node=current_node())


@contextmanager
def command_origin_scope(origin: CommandOrigin):
    token = _origin.set(origin)
    try:
        yield
    finally:
        _origin.reset(token)


class BackgroundCommandError(RuntimeError):
    """A critical command failed, retaining its submitting workflow context."""

    def __init__(self, origin, component, command, cause):
        self.origin, self.component, self.command = origin, component, command
        self.cause = cause
        location = ", ".join(
            f"{key}={value}"
            for key, value in (
                ("process", origin.process),
                ("node", origin.node),
                ("iteration", origin.iteration),
            )
            if value is not None
        )
        super().__init__(
            f"Background command {component}.{command} failed ({location}): {cause}"
        )
        self.__cause__ = cause


@dataclass
class _CommandJob:
    fn: Callable
    future: Future
    origin: CommandOrigin
    component: str
    command: str
    critical: bool


_STOP = object()


class BackgroundTasks:
    """Own background graph threads and one FIFO command worker per client."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._threads: list[threading.Thread] = []
        self._workers: dict[object, tuple[queue.Queue, threading.Thread]] = {}
        self._pending: dict[Future, object] = {}
        self._command_stop = threading.Event()
        self._command_error: BackgroundCommandError | None = None
        self._commands_closed = False

    @property
    def has_tasks(self) -> bool:
        with self._lock:
            return bool(self._threads)

    def submit(self, fn: Callable[[], None], name: str) -> None:
        thread = threading.Thread(target=fn, name=f"background-{name}", daemon=True)
        with self._lock:
            self._threads.append(thread)
        thread.start()

    def join(self, timeout: float) -> list[str]:
        """Wait up to timeout for all threads; return names still running."""
        with self._lock:
            threads = list(self._threads)
        deadline = time.monotonic() + timeout
        for thread in threads:
            thread.join(max(0.0, deadline - time.monotonic()))
        return [thread.name for thread in threads if thread.is_alive()]

    @property
    def commands_finished(self) -> bool:
        """A closed host can be replaced when reusing a standalone platform."""
        with self._lock:
            return self._commands_closed and all(
                not thread.is_alive() for _, thread in self._workers.values()
            )

    @property
    def commands_cancelled(self) -> bool:
        return self._command_stop.is_set()

    def has_command_queue(self, key: object) -> bool:
        with self._lock:
            return key in self._workers

    def in_command_worker(self, key: object) -> bool:
        with self._lock:
            worker = self._workers.get(key)
            return worker is not None and worker[1] is threading.current_thread()

    def check_command_errors(self) -> None:
        with self._lock:
            error = self._command_error
        if error is not None:
            raise error

    def _cancel_commands(self) -> None:
        with self._lock:
            self._command_stop.set()
            for future in tuple(self._pending):
                future.cancel()

    def submit_command(
        self,
        fn: Callable,
        name: str,
        *,
        key: object,
        component: str,
        command: str,
        origin: CommandOrigin | None = None,
        critical: bool = True,
    ) -> Future:
        future: Future = Future()
        job = _CommandJob(
            fn, future, origin or current_command_origin(), component, command, critical
        )
        with self._lock:
            self.check_command_errors()
            if self._commands_closed:
                raise RuntimeError("Background command host is closed")
            if self.commands_cancelled:
                future.cancel()
                return future
            self._pending[future] = key
            future.add_done_callback(self._forget_command)
            if key not in self._workers:
                tasks: queue.Queue = queue.Queue()
                thread = threading.Thread(
                    target=self._command_worker,
                    args=(tasks,),
                    name=f"background-command-{name}",
                    daemon=True,
                )
                self._workers[key] = (tasks, thread)
                self._threads.append(thread)
                thread.start()
            self._workers[key][0].put(job)
        return future

    def _forget_command(self, future: Future) -> None:
        with self._lock:
            self._pending.pop(future, None)

    def _command_worker(self, tasks: queue.Queue) -> None:
        while True:
            job = tasks.get()
            try:
                if job is _STOP:
                    return
                with self._lock:
                    if self.commands_cancelled:
                        job.future.cancel()
                    if not job.future.set_running_or_notify_cancel():
                        continue
                previous_node = current_node()
                set_current_node(job.origin.node)
                try:
                    with command_origin_scope(job.origin):
                        result = job.fn()
                except RunCancelledError as exc:
                    self._cancel_commands()
                    job.future.set_exception(exc)
                except Exception as exc:
                    failure = exc
                    with self._lock:
                        if job.critical and not self.commands_cancelled:
                            failure = BackgroundCommandError(
                                job.origin, job.component, job.command, exc
                            )
                            self._command_error = self._command_error or failure
                            self._cancel_commands()
                    job.future.set_exception(failure)
                else:
                    job.future.set_result(result)
                finally:
                    set_current_node(previous_node)
            finally:
                tasks.task_done()

    def wait_for_commands(self, key=None, checkpoint=None) -> None:
        """Wait for a snapshot of submitted work, without waiting for graph nodes."""
        with self._lock:
            pending = {f for f, k in self._pending.items() if key is None or k == key}
        while pending:
            self.check_command_errors()
            if checkpoint is not None:
                checkpoint()
            done, pending = wait(pending, timeout=0.1)
            # A critical failure cancels other futures. Always surface that
            # retained cause before inspecting the newly cancelled futures.
            self.check_command_errors()
            for future in done:
                if future.cancelled():
                    raise RunCancelledError("Pending command was cancelled.")
                future.result()
        self.check_command_errors()
        if checkpoint is not None:
            checkpoint()

    def close_commands(self, cancel=False, checkpoint=None) -> None:
        with self._lock:
            self._commands_closed = True
        try:
            if cancel:
                self._cancel_commands()
            else:
                self.wait_for_commands(checkpoint=checkpoint)
        except BaseException:
            self._cancel_commands()
            raise
        finally:
            with self._lock:
                self._command_stop.set()
                workers = tuple(self._workers.values())
                for tasks, _ in workers:
                    tasks.put(_STOP)
            for _, thread in workers:
                if thread is not threading.current_thread():
                    thread.join()
