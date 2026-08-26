# Script file of project parameter
# Updated/Created on: 2026-04-22T11:24:58.037258+00:00
# Project name: complete
from __future__ import annotations

import time

import networkx as nx
from pydantic import BaseModel, ConfigDict

from chemunited_workflow import (
    NodeExecutionContext,
    Process,
    WorkflowEdgeSpec,
    WorkflowNodeSpec,
)

# ── Process configuration ──────────────────────────────────────────────────────


class ProcessConfig(BaseModel):
    pass

    model_config = ConfigDict(frozen=True)

    # Add your process-level parameters here
    # Example:
    # flow_rate: str = "5 ml/min"


# ── Process class ──────────────────────────────────────────────────────────────


class CustomProcess(Process[ProcessConfig]):
    """User-defined workflow process."""

    def build_workflow(self) -> nx.DiGraph:
        graph: nx.DiGraph = nx.DiGraph()

        graph.add_node(
            "start",
            **WorkflowNodeSpec(
                node_id="start",
                method="start",
                position=(-11.607142857142833, 298.2142857142858),
            ).model_dump(exclude_none=True),
            block_tag="start",
        )

        graph.add_node(
            "end",
            **WorkflowNodeSpec(
                node_id="end",
                method="finish",
                position=(1469.1258902773764, 286.183241203712),
            ).model_dump(exclude_none=True),
            block_tag="end",
        )

        graph.add_node(
            "conditional_1",
            **WorkflowNodeSpec(
                node_id="conditional_1",
                method="conditional_1",
                position=(414.2673964671434, 159.7141141969438),
            ).model_dump(exclude_none=True),
            block_tag="if",
        )

        graph.add_node(
            "script_1",
            **WorkflowNodeSpec(
                node_id="script_1",
                method="script_1",
                position=(715.1809028845425, 35.244942511821606),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "loop_1",
            **WorkflowNodeSpec(
                node_id="loop_1",
                method="loop_1",
                position=(1129.026575925248, 63.16232592588801),
            ).model_dump(exclude_none=True),
            block_tag="loop",
        )

        graph.add_node(
            "command_1",
            **WorkflowNodeSpec(
                node_id="command_1",
                method="command_1",
                position=(875.0, 351.0),
            ).model_dump(exclude_none=True),
            block_tag="command",
        )

        graph.add_edge(
            "start",
            "conditional_1",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "conditional_1",
            "script_1",
            **WorkflowEdgeSpec(
                condition=False,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "conditional_1",
            "command_1",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_1",
            "loop_1",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "loop_1",
            "end",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "loop_1",
            "script_1",
            loopback=True,
            trigger_on=False,
            inflection_points=[(622.6932742620384, 95.38849021885483)],
        )

        graph.add_edge(
            "command_1",
            "end",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        return graph

    # ── Node methods ───────────────────────────────────────────────────────────

    def start(self, ctx: NodeExecutionContext) -> bool:
        ctx.runtime.status_message = "Started."
        return True

    def finish(self, ctx: NodeExecutionContext) -> bool:
        ctx.runtime.status_message = "Finished."
        return True

    def conditional_1(self, ctx: NodeExecutionContext) -> bool:
        ctx.runtime.status_message = "Conditional 1 ran."
        return True

    def script_1(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Script 1 starting.")
        time.sleep(0.4)
        ctx.report_progress(
            50, "Script 1 waiting for reaction to settle.", wait_seconds=5
        )
        time.sleep(5)
        ctx.report_progress(100, "Script 1 ran.")
        return True

    def loop_1(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Loop 1 evaluating exit condition.")
        time.sleep(0.3)
        ctx.report_progress(100, "Loop 1 ran.")
        return True

    def command_1(self, ctx: NodeExecutionContext) -> bool:
        from loguru import logger

        ctx.report_progress(0, "Command 1 starting: moving AS injection valve.")

        logger.info("Process clean: Command 1 started.")
        self.platform["AS injection"].put(
            "position",
            connect="[[1, 2]]",
            disconnect="",
        )
        logger.info("Process clean: Command 1 finished.")

        ctx.report_progress(100, "Command 1 ran.")
        return True
