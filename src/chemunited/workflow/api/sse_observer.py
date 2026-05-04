from __future__ import annotations

import asyncio

from chemunited.workflow.models import WorkflowExecutionEvent


class APIWorkflowObserver:
    """Bridges synchronous workflow events to an asyncio.Queue for SSE streaming.

    handle_event is called from a worker thread; it schedules the put on the
    event loop via call_soon_threadsafe so the queue stays thread-safe.
    The caller is responsible for enqueuing the None sentinel to close the stream.
    """

    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[WorkflowExecutionEvent | None],
    ) -> None:
        self._loop = loop
        self._queue = queue

    def handle_event(self, event: WorkflowExecutionEvent) -> None:
        self._loop.call_soon_threadsafe(self._queue.put_nowait, event)
