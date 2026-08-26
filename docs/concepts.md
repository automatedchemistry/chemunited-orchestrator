# Concepts

## How Execution Works

1. **Graph definition** — `build_workflow()` returns a `networkx.DiGraph` where each node has a `method` attribute pointing to a method on the `Process` class, and edges carry boolean `condition` values.
2. **Compilation** — `compile_workflow()` validates the graph, extracts loopback edges (cycles), and ensures the remaining graph is a DAG.
3. **Execution** — `WorkflowExecutor` traverses the compiled graph using a `ThreadPoolExecutor`: nodes whose predecessors have all completed are scheduled concurrently; edge conditions are evaluated to route execution; loopbacks are triggered when a node returns `True` to repeat a section.
4. **Events** — The executor emits `WorkflowExecutionEvent` objects for each state transition, consumed by the API to provide real-time status and log streaming.
5. **Result** — A `WorkflowResult` is returned with the final state, per-node results, runtime, and any errors.

## Node Progress Feedback

Every node method receives a `NodeExecutionContext` (`ctx`). Beyond `ctx.process`, `ctx.config`, and `ctx.node_config`, it carries `ctx.runtime` (a `NodeRuntime`) and a live callback for pushing progress from *inside* a running method:

```python
def dose_reagent(self, ctx: NodeExecutionContext) -> bool:
    ctx.report_progress(0, "Priming line.")
    self.platform["reagent_pump"].put("infuse", volume="2 ml", rate="10 ml/min")

    ctx.report_progress(60, "Reagent dosed, flushing line.")
    self.platform["reagent_pump"].put("infuse", volume="0.5 ml", rate="10 ml/min")

    ctx.report_progress(100, "Dosing complete.")
    return True
```

- **`ctx.report_progress(percentage, message=None, wait_seconds=None)`** emits a `NODE_PROGRESS` event immediately — not just at node start/finish — so anything watching the event stream (the dashboard's Run Control page, a custom listener, `GET /run/status`) sees the update while the node is still executing. `percentage` is clamped to `0`–`100`; `message` is optional — omit it to update only the percentage.
- **`wait_seconds`** — pass a duration (e.g. right before a fixed `self.platform._wait(seconds)` delay) to let clients render a live countdown. It's a fire-once hint carried only on that one event, not persisted run history; the next `report_progress` call (or any other event for that node) that omits it signals the countdown should be cleared. The bundled dashboard renders this as a depleting clock next to the node's message — see [HTML UI](html-ui.md#live-node-progress).
- **Auto-managed baseline** — you don't have to call `report_progress` at all. The executor resets `status_percentage` to `0` when a node starts running and sets it to `100` when it completes, so every node always has a sane value. `report_progress` is opt-in, for finer-grained detail inside longer-running methods.
- **Live snapshot, not a log** — each call overwrites `runtime.status_message` / `runtime.status_percentage` in place. There's no history; it's "what's happening right now" for that node. If you need a durable record of intermediate steps, log them separately (e.g. via `loguru`) rather than relying on progress messages.
- **Where it surfaces** — `NodeRuntime.status_message` / `status_percentage` are included in `WorkflowResult.model_dump()` (`node_runtime` map) for post-run inspection, and every `NODE_PROGRESS` event carries `node_key`, `percentage`, and `message` over `/run/stream` (SSE) and `/run/status` (polling) — see [API Reference](api-reference.md#run-control). The bundled dashboard renders one row per node under its process card, with a live progress bar and label — see [HTML UI](html-ui.md#live-node-progress).
- Assigning `ctx.runtime.status_message` directly (an older convention still visible in some example protocols) has **no visible effect**: the executor overwrites `status_message` itself at every lifecycle transition (`"Running method '...'."`, `"Node completed with result ...."`), so a manual mid-method assignment is always clobbered before anything reads it. Use `report_progress` for any message you want to actually reach the dashboard or event stream.

## Human-in-the-Loop Input

A node can pause and wait for an operator to answer a prompt on the dashboard, then resume using their reply:

```python
def confirm_setup(self, ctx: NodeExecutionContext) -> bool:
    reply = ctx.request_operator_input(
        "Confirm reagent loaded (yes/no).", timeout_seconds=300
    )
    return reply.strip().lower() == "yes"
```

- **`ctx.request_operator_input(message, timeout_seconds)`** blocks the calling node's worker thread — other nodes keep running — and shows `message` on the dashboard as a prompt tied to that node's row (see [HTML UI → Operator input prompts](html-ui.md#operator-input-prompts)). It returns whatever the operator typed, as a string.
- **`timeout_seconds` is required, with no default** — there's no call shape that waits forever. If nobody replies in time, the wait raises `OperatorInputTimeoutError`, which propagates like any other node exception: the node is marked `FAILED` and its successors become `INACTIVE` (respecting `error_resilient`, same as any other error — see [API Reference → Run control](api-reference.md#run-control)).
- **Cancelling the run** while a node is waiting raises `RunCancelledError` in that node, same as cancelling anywhere else.
- **Scoped per node** — concurrent branches can each be waiting on their own prompt independently; replying to one doesn't affect the others.
- **Not persisted across a server restart** — like the rest of run state, a pending prompt lives only in memory. A dashboard client that reconnects mid-wait (without a restart) still recovers the open prompt, via `GET /run/active`'s `pending_inputs` field.
- Requires a run driven by the dashboard/API — calling it outside that context (e.g. a bare `WorkflowExecutor.execute(...)` with no `request_input` wired) raises `RuntimeError` immediately.

## Physical Units

Use `ChemUnitQuantity` from `chemunited-quantities` for values that carry SI units:

```python
from chemunited_quantities import ChemUnitQuantity

volume = ChemUnitQuantity.parse("500 ul")
double = volume * 2          # 1000 ul
in_ml  = volume.to("ml")     # 0.5 ml
```

Units are validated and propagated through arithmetic. Import
`ChemQuantityValidator` directly from `chemunited_quantities` for Pydantic models.

## Dry-Run Mode

Pass `dry_run=True` to `Platform` to suppress all HTTP calls — useful for testing graph logic without hardware:

```python
platform = Platform.from_connectivity(path, dry_run=True)
```

---

[← Back to README](../README.md)
