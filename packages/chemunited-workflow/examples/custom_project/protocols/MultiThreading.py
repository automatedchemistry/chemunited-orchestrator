# Script file of project parameter
# Updated/Created on: 2026-04-22T10:13:51.634077+00:00
# Project name: complete
from __future__ import annotations

import time
from typing import TYPE_CHECKING

import networkx as nx
from pydantic import BaseModel, ConfigDict

from chemunited_workflow import (
    NodeExecutionContext,
    Process,
    WorkflowEdgeSpec,
    WorkflowNodeSpec,
)

if TYPE_CHECKING:
    pass


# ── Process configuration ──────────────────────────────────────────────────────


class ProcessConfig(BaseModel):
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
                position=(-397.0, 255.0),
            ).model_dump(exclude_none=True),
            block_tag="start",
        )

        graph.add_node(
            "end",
            **WorkflowNodeSpec(
                node_id="end",
                method="finish",
                position=(2319.2832199065606, 185.51828425932786),
            ).model_dump(exclude_none=True),
            block_tag="end",
        )

        graph.add_node(
            "script_1",
            **WorkflowNodeSpec(
                node_id="script_1",
                method="script_1",
                position=(-118.0, 173.0),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "script_2",
            **WorkflowNodeSpec(
                node_id="script_2",
                method="script_2",
                position=(251.0, 16.0),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "script_3",
            **WorkflowNodeSpec(
                node_id="script_3",
                method="script_3",
                position=(243.0, 270.0),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "script_4",
            **WorkflowNodeSpec(
                node_id="script_4",
                method="script_4",
                position=(640.0, -135.0),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "script_5",
            **WorkflowNodeSpec(
                node_id="script_5",
                method="script_5",
                position=(678.8822323200001, 26.956093439999975),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "loop_1",
            **WorkflowNodeSpec(
                node_id="loop_1",
                method="loop_1",
                position=(1081.0, -25.0),
            ).model_dump(exclude_none=True),
            block_tag="loop",
        )

        graph.add_node(
            "conditional_1",
            **WorkflowNodeSpec(
                node_id="conditional_1",
                method="conditional_1",
                position=(651.8549417820161, 363.18337407385616),
            ).model_dump(exclude_none=True),
            block_tag="if",
        )

        graph.add_node(
            "script_6",
            **WorkflowNodeSpec(
                node_id="script_6",
                method="script_6",
                position=(947.4348888883203, 219.09431805542403),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "script_7",
            **WorkflowNodeSpec(
                node_id="script_7",
                method="script_7",
                position=(937.5657754624006, 453.97921759232),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "script_8",
            **WorkflowNodeSpec(
                node_id="script_8",
                method="script_8",
                position=(1340.2256032399362, 345.4189699072),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "script_9",
            **WorkflowNodeSpec(
                node_id="script_9",
                method="script_9",
                position=(1640.2466513879044, 155.93199212953604),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "script_10",
            **WorkflowNodeSpec(
                node_id="script_10",
                method="script_10",
                position=(1650.115764813824, 471.743621758976),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "script_11",
            **WorkflowNodeSpec(
                node_id="script_11",
                method="script_11",
                position=(2003.430025461761, 27.633517592575995),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_edge(
            "start",
            "script_1",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_1",
            "script_2",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_1",
            "script_3",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_2",
            "script_4",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_2",
            "script_5",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_3",
            "conditional_1",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_4",
            "loop_1",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_5",
            "loop_1",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "loop_1",
            "script_11",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "loop_1",
            "script_2",
            loopback=True,
            trigger_on=False,
        )

        graph.add_edge(
            "conditional_1",
            "script_6",
            **WorkflowEdgeSpec(
                condition=False,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "conditional_1",
            "script_7",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_6",
            "script_8",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_7",
            "script_8",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_8",
            "script_9",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_8",
            "script_10",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_9",
            "script_11",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_10",
            "script_11",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_11",
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

    def script_1(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Script 1 fanning out into two branches.")
        time.sleep(0.3)
        ctx.report_progress(60, "Script 1 preparing branch inputs.")
        time.sleep(0.3)
        ctx.report_progress(100, "Script 1 ran.")
        return True

    def script_2(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Script 2 (branch A) starting.")
        time.sleep(0.3)
        ctx.report_progress(45, "Script 2 (branch A) working.")
        time.sleep(0.3)
        ctx.report_progress(100, "Script 2 ran.")
        return True

    def script_3(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Script 3 (branch B) starting.")
        time.sleep(0.3)
        ctx.report_progress(45, "Script 3 (branch B) working.")
        time.sleep(0.3)
        ctx.report_progress(100, "Script 3 ran.")
        return True

    def script_4(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Script 4 (branch A.1) starting.")
        time.sleep(0.2)
        ctx.report_progress(70, "Script 4 (branch A.1) almost done.")
        time.sleep(0.2)
        ctx.report_progress(100, "Script 4 ran.")
        return True

    def script_5(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Script 5 (branch A.2) starting.")
        time.sleep(0.2)
        ctx.report_progress(70, "Script 5 (branch A.2) almost done.")
        time.sleep(0.2)
        ctx.report_progress(100, "Script 5 ran.")
        return True

    def loop_1(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Loop 1 evaluating branch join.")
        time.sleep(0.3)
        ctx.report_progress(100, "Loop 1 ran.")
        return True

    def conditional_1(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Conditional 1 checking branch B result.")
        time.sleep(0.2)
        ctx.report_progress(100, "Conditional 1 ran.")
        return True

    def script_6(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Script 6 (branch B.1) starting.")
        time.sleep(0.2)
        ctx.report_progress(55, "Script 6 (branch B.1) working.")
        time.sleep(0.2)
        ctx.report_progress(100, "Script 6 ran.")
        return True

    def script_7(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Script 7 (branch B.2) starting.")
        time.sleep(0.2)
        ctx.report_progress(55, "Script 7 (branch B.2) working.")
        time.sleep(0.2)
        ctx.report_progress(100, "Script 7 ran.")
        return True

    def script_8(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Script 8 joining branches A and B.")
        time.sleep(0.3)
        ctx.report_progress(50, "Script 8 merging results.")
        time.sleep(0.3)
        ctx.report_progress(100, "Script 8 ran.")
        return True

    def script_9(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Script 9 starting.")
        time.sleep(0.2)
        ctx.report_progress(80, "Script 9 finishing up.")
        time.sleep(0.2)
        ctx.report_progress(100, "Script 9 ran.")
        return True

    def script_10(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Script 10 starting.")
        time.sleep(0.2)
        ctx.report_progress(80, "Script 10 finishing up.")
        time.sleep(0.2)
        ctx.report_progress(100, "Script 10 ran.")
        return True

    def script_11(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Script 11 finalizing all branches.")
        time.sleep(0.3)
        ctx.report_progress(65, "Script 11 wrapping up.")
        time.sleep(0.3)
        ctx.report_progress(100, "Script 11 ran.")
        return True
