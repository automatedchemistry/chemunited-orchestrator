"""Thread-safe execution engine for compiled workflows."""

from __future__ import annotations

from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from threading import RLock
from time import perf_counter
from typing import TYPE_CHECKING, Any, Callable, Sequence

import networkx as nx
from loguru import logger

from .enums import NodeState, WorkflowEventType
from .models import (
    CompiledWorkflow,
    LoopBackSpec,
    NodeConfig,
    NodeExecutionContext,
    NodeRuntime,
    WorkflowExecutionEvent,
    WorkflowExecutorState,
    WorkflowResult,
)

if TYPE_CHECKING:
    from .process import Process

NodeKey = tuple[str, int]
EventListener = Callable[[WorkflowExecutionEvent], None]


@dataclass(slots=True)
class _NodeOutcome:
    """Internal node execution result."""

    node_key: NodeKey
    result: bool


class WorkflowExecutor:
    """Execute compiled workflow DAGs with loopbacks handled outside the DAG."""

    def __init__(
        self,
        compiled_workflow: CompiledWorkflow,
        max_workers: int | None = None,
        event_listeners: Sequence[EventListener] | None = None,
    ) -> None:
        self._compiled = compiled_workflow
        self._max_workers = max_workers
        self._lock = RLock()
        self._logger = logger.bind(component="workflow.executor")
        self._event_listeners = tuple(event_listeners or ())

        self._state = WorkflowExecutorState()
        self._loopbacks_by_trigger: dict[tuple[str, bool], LoopBackSpec] = {}
        self._reachable_nodes: dict[int, set[str]] = {}
        self._iteration_roots: dict[int, NodeKey] = {}
        self._expected_predecessors: dict[NodeKey, set[NodeKey]] = {}
        self._resolved_predecessors: dict[NodeKey, set[NodeKey]] = {}
        self._inactive_propagated: set[NodeKey] = set()
        self._future_to_key: dict[Future[_NodeOutcome], NodeKey] = {}
        self._stop_scheduling = False
        self._pool: ThreadPoolExecutor | None = None
        self._process: Process[Any] | None = None

    def execute(self, process: Process[Any], start_node: str) -> WorkflowResult:
        """Execute the compiled workflow starting from ``start_node``."""

        if start_node not in self._compiled.exec_graph:
            raise ValueError(f"Start node {start_node!r} is not present in the executable graph.")

        self._state = WorkflowExecutorState()
        self._reachable_nodes = {}
        self._iteration_roots = {}
        self._expected_predecessors = {}
        self._resolved_predecessors = {}
        self._inactive_propagated = set()
        self._future_to_key = {}
        self._stop_scheduling = False
        self._process = process
        self._loopbacks_by_trigger = {
            (loopback.source, loopback.trigger_on): loopback for loopback in self._compiled.loopbacks
        }
        self._emit_event(
            event_type=WorkflowEventType.EXECUTION_STARTED,
            message=(
                f"Execution started for process {type(process).__name__} at start node {start_node!r}."
            ),
        )

        execution_error: Exception | None = None
        try:
            with ThreadPoolExecutor(max_workers=self._max_workers, thread_name_prefix="workflow") as pool:
                self._pool = pool
                self._initialize_iteration(start_node=start_node, iteration=0)

                while self._future_to_key:
                    done, _ = wait(tuple(self._future_to_key), return_when=FIRST_COMPLETED)
                    for future in done:
                        node_key = self._future_to_key.pop(future)
                        self._handle_completed_future(node_key=node_key, future=future)
        except Exception as exc:
            execution_error = exc
            raise
        finally:
            result_snapshot = WorkflowResult(
                node_state=dict(self._state.node_state),
                node_result=dict(self._state.node_result),
                node_runtime=dict(self._state.node_runtime),
                errors=dict(self._state.errors),
            )
            if execution_error is None:
                final_message = (
                    f"Execution finished with {len(result_snapshot.errors)} error(s) across "
                    f"{len(result_snapshot.node_state)} tracked node execution(s)."
                )
            else:
                final_message = (
                    f"Execution aborted with {type(execution_error).__name__}: {execution_error}. "
                    f"Tracked {len(result_snapshot.node_state)} node execution(s) before shutdown."
                )
            self._emit_event(
                event_type=WorkflowEventType.EXECUTION_FINISHED,
                message=final_message,
            )

        return WorkflowResult(
            node_state=dict(self._state.node_state),
            node_result=dict(self._state.node_result),
            node_runtime=dict(self._state.node_runtime),
            errors=dict(self._state.errors),
        )

    def _initialize_iteration(self, start_node: str, iteration: int) -> None:
        if self._process is None or self._pool is None:
            raise RuntimeError("WorkflowExecutor.execute() must be called before scheduling iterations.")

        if iteration in self._iteration_roots:
            existing_root = self._iteration_roots[iteration]
            raise RuntimeError(
                "A second workflow start was requested for the same iteration index. "
                f"Iteration {iteration} is already rooted at {existing_root[0]!r}."
            )

        reachable_nodes = set(nx.descendants(self._compiled.exec_graph, start_node))
        reachable_nodes.add(start_node)
        self._reachable_nodes[iteration] = reachable_nodes
        self._emit_event(
            event_type=WorkflowEventType.ITERATION_STARTED,
            message=f"Iteration {iteration} started at node {start_node!r}.",
            node_key=(start_node, iteration),
        )

        for node_id in self._compiled.exec_graph.nodes:
            node_key = (node_id, iteration)
            self._ensure_node_entry(node_key)

            if node_id in reachable_nodes:
                expected = {
                    (predecessor, iteration)
                    for predecessor in self._compiled.exec_graph.predecessors(node_id)
                    if predecessor in reachable_nodes
                }
                self._expected_predecessors[node_key] = expected
                self._resolved_predecessors[node_key] = set()
            else:
                self._expected_predecessors[node_key] = set()
                self._resolved_predecessors[node_key] = set()
                self._update_node_status(
                    node_key,
                    state=NodeState.INACTIVE,
                    message="Node is outside the reachable subgraph for this iteration.",
                    event_type=WorkflowEventType.NODE_INACTIVE,
                )

        root_key = (start_node, iteration)
        self._iteration_roots[iteration] = root_key
        self._update_node_status(
            root_key,
            state=NodeState.WAITING,
            message="Iteration root is ready to run.",
            event_type=WorkflowEventType.NODE_WAITING,
        )
        self._maybe_schedule(root_key)

    def _ensure_node_entry(self, node_key: NodeKey) -> None:
        self._state.node_state.setdefault(node_key, NodeState.NOT_VISITED)
        self._state.node_result.setdefault(node_key, None)
        self._state.node_runtime.setdefault(node_key, NodeRuntime())
        self._state.active_predecessors.setdefault(node_key, set())
        self._state.completed_predecessors.setdefault(node_key, set())
        self._state.scheduled.setdefault(node_key, False)

    def _maybe_schedule(self, node_key: NodeKey) -> None:
        if self._stop_scheduling:
            return

        state = self._state.node_state[node_key]
        if self._state.scheduled[node_key] or state in {
            NodeState.RUNNING,
            NodeState.COMPLETED,
            NodeState.FAILED,
            NodeState.INACTIVE,
        }:
            return

        expected = self._expected_predecessors[node_key]
        resolved = self._resolved_predecessors[node_key]

        if node_key == self._iteration_roots[node_key[1]]:
            self._submit_node(node_key)
            return

        if resolved != expected:
            missing = len(expected - resolved)
            self._update_node_status(
                node_key,
                state=NodeState.WAITING,
                message=f"Waiting for {missing} predecessor resolution(s).",
                event_type=WorkflowEventType.NODE_WAITING,
            )
            return

        if self._state.active_predecessors[node_key]:
            self._submit_node(node_key)
            return

        self._mark_node_inactive(
            node_key,
            "Node was not activated by any predecessor in this iteration.",
        )

    def _submit_node(self, node_key: NodeKey) -> None:
        if self._process is None or self._pool is None:
            raise RuntimeError("WorkflowExecutor.execute() must be called before submitting nodes.")

        node_id, _ = node_key
        method_name = self._compiled.exec_graph.nodes[node_id].get("method")

        self._state.scheduled[node_key] = True
        self._update_node_status(
            node_key,
            state=NodeState.RUNNING,
            message=f"Running method '{method_name}'.",
            event_type=WorkflowEventType.NODE_RUNNING,
            method=method_name,
        )
        future = self._pool.submit(self._execute_node, node_key)
        self._future_to_key[future] = node_key

    def _execute_node(self, node_key: NodeKey) -> _NodeOutcome:
        if self._process is None:
            raise RuntimeError("WorkflowExecutor.execute() must be called before running nodes.")

        node_id, iteration = node_key
        node_data = self._compiled.exec_graph.nodes[node_id]
        method_name = node_data["method"]
        node_config = node_data.get("node_config")

        if node_config is not None and not isinstance(node_config, NodeConfig):
            raise TypeError(
                f"Node {node_id!r} has invalid node_config type {type(node_config).__name__!r}."
            )

        try:
            method = getattr(self._process, method_name)
        except AttributeError as exc:
            raise AttributeError(
                f"Process {type(self._process).__name__} has no workflow method named {method_name!r} "
                f"for node {node_id!r}."
            ) from exc

        if not callable(method):
            raise TypeError(
                f"Resolved attribute {method_name!r} for node {node_id!r} is not callable."
            )

        runtime = self._state.node_runtime[node_key]
        with self._lock:
            runtime.started_at = perf_counter()
            runtime.status_message = f"Running method '{method_name}'."

        ctx = NodeExecutionContext(
            node_id=node_id,
            iteration=iteration,
            process=self._process,
            config=self._process.config,
            node_config=node_config,
            runtime=runtime,
        )

        try:
            result = method(ctx)
            if not isinstance(result, bool):
                raise TypeError(
                    f"Workflow method {method_name!r} for node {node_id!r} returned {result!r}. "
                    "Workflow methods must return bool."
                )
            with self._lock:
                runtime.result = result
                runtime.error = None
                runtime.status_message = f"Method '{method_name}' completed with result {result}."
            return _NodeOutcome(node_key=node_key, result=result)
        except Exception as exc:
            with self._lock:
                runtime.error = exc
                runtime.status_message = f"Method '{method_name}' failed: {exc}"
            raise
        finally:
            with self._lock:
                runtime.finished_at = perf_counter()

    def _handle_completed_future(self, node_key: NodeKey, future: Future[_NodeOutcome]) -> None:
        try:
            outcome = future.result()
        except Exception as exc:
            self._state.errors[node_key] = exc
            self._state.node_result[node_key] = None
            self._stop_scheduling = True
            self._update_node_status(
                node_key,
                state=NodeState.FAILED,
                message=f"Node execution failed: {exc}",
                event_type=WorkflowEventType.NODE_FAILED,
            )
            return

        self._state.node_result[node_key] = outcome.result
        self._update_node_status(
            node_key,
            state=NodeState.COMPLETED,
            message=f"Node completed with result {outcome.result}.",
            event_type=WorkflowEventType.NODE_COMPLETED,
            result=outcome.result,
            method=self._compiled.exec_graph.nodes[node_key[0]].get("method"),
        )
        self._route_after_completion(node_key=node_key, result=outcome.result)

    def _route_after_completion(self, node_key: NodeKey, result: bool) -> None:
        node_id, iteration = node_key
        loopback = self._loopbacks_by_trigger.get((node_id, result))

        for _, successor, edge_data in self._compiled.exec_graph.out_edges(node_id, data=True):
            successor_key = (successor, iteration)
            condition = edge_data["condition"]
            should_activate = condition is result and loopback is None
            self._resolve_predecessor(
                node_key=successor_key,
                predecessor_key=node_key,
                is_active=should_activate,
            )

        if loopback is not None:
            next_iteration = iteration + 1
            if loopback.max_iterations is not None and next_iteration > loopback.max_iterations:
                raise RuntimeError(
                    "Loopback iteration guard exceeded. "
                    f"Loopback {loopback.source!r} -> {loopback.target!r} requested iteration "
                    f"{next_iteration}, but max_iterations={loopback.max_iterations}."
                )

            loopback_message = (
                f"Completed with result {result}; triggered loopback to {loopback.target!r} "
                f"for iteration {next_iteration}."
            )
            self._state.node_runtime[node_key].status_message = loopback_message
            self._emit_event(
                event_type=WorkflowEventType.LOOPBACK_TRIGGERED,
                message=loopback_message,
                node_key=node_key,
                result=result,
                source=loopback.source,
                target=loopback.target,
            )
            self._initialize_iteration(start_node=loopback.target, iteration=next_iteration)

    def _resolve_predecessor(self, node_key: NodeKey, predecessor_key: NodeKey, is_active: bool) -> None:
        expected = self._expected_predecessors.get(node_key)
        if expected is None or predecessor_key not in expected:
            return

        resolved = self._resolved_predecessors[node_key]
        if predecessor_key in resolved:
            return

        resolved.add(predecessor_key)

        if is_active:
            self._state.active_predecessors[node_key].add(predecessor_key)
            self._state.completed_predecessors[node_key].add(predecessor_key)
            self._update_node_status(
                node_key,
                state=NodeState.WAITING,
                message="Activated; waiting for other predecessor resolutions.",
                event_type=WorkflowEventType.NODE_WAITING,
            )
        else:
            if self._state.node_state[node_key] == NodeState.NOT_VISITED:
                self._state.node_state[node_key] = NodeState.WAITING
            missing = len(expected - resolved)
            self._update_node_status(
                node_key,
                state=NodeState.WAITING,
                message=f"Waiting for {missing} predecessor resolution(s).",
                event_type=WorkflowEventType.NODE_WAITING,
            )

        self._maybe_schedule(node_key)

    def _mark_node_inactive(self, node_key: NodeKey, reason: str) -> None:
        state = self._state.node_state[node_key]
        if state in {NodeState.COMPLETED, NodeState.RUNNING, NodeState.FAILED}:
            return

        self._state.node_result[node_key] = None
        self._update_node_status(
            node_key,
            state=NodeState.INACTIVE,
            message=reason,
            event_type=WorkflowEventType.NODE_INACTIVE,
        )

        if node_key in self._inactive_propagated:
            return
        self._inactive_propagated.add(node_key)

        node_id, iteration = node_key
        for successor in self._compiled.exec_graph.successors(node_id):
            successor_key = (successor, iteration)
            self._resolve_predecessor(
                node_key=successor_key,
                predecessor_key=node_key,
                is_active=False,
            )

    def _update_node_status(
        self,
        node_key: NodeKey,
        *,
        state: NodeState,
        message: str,
        event_type: WorkflowEventType,
        result: bool | None = None,
        method: str | None = None,
    ) -> None:
        self._state.node_state[node_key] = state
        self._state.node_runtime[node_key].status_message = message
        self._emit_event(
            event_type=event_type,
            message=message,
            node_key=node_key,
            state=state,
            result=result,
            method=method,
        )

    def _emit_event(
        self,
        *,
        event_type: WorkflowEventType,
        message: str,
        node_key: NodeKey | None = None,
        state: NodeState | None = None,
        result: bool | None = None,
        method: str | None = None,
        source: str | None = None,
        target: str | None = None,
    ) -> None:
        event = WorkflowExecutionEvent(
            event_type=event_type,
            message=message,
            node_key=node_key,
            state=state,
            result=result,
            method=method,
            source=source,
            target=target,
            active_predecessor_count=(
                len(self._state.active_predecessors.get(node_key, set())) if node_key is not None else None
            ),
            completed_predecessor_count=(
                len(self._state.completed_predecessors.get(node_key, set()))
                if node_key is not None
                else None
            ),
        )

        for listener in self._event_listeners:
            try:
                listener(event)
            except Exception as exc:
                self._logger.warning("Workflow event listener failed: {}", exc)
