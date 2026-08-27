# Script file of project parameter
# Updated/Created on: 2026-04-24T16:15:02.029103+00:00
# Project name: complete

from typing import TYPE_CHECKING, Annotated, Literal

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from chemunited_quantities import ChemQuantityValidator, ChemUnitQuantity
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

    branch_timeout: Annotated[ChemUnitQuantity, ChemQuantityValidator("s")] = Field(
        title="Branch Timeout",
        description="Maximum time to wait for each parallel branch to finish.",
        default=ChemUnitQuantity("120 s"),
        json_schema_extra={
            "group": "Parallel Execution",
            "editable": True,
            "visible": True,
            "unit": "s",
        },
    )

    retry_count: int = Field(
        title="Retry Count",
        description="Number of retry attempts allowed for a failed branch step.",
        default=1,
        ge=0,
        le=5,
        json_schema_extra={
            "group": "Parallel Execution",
            "editable": True,
            "visible": True,
        },
    )

    parallel_branch_policy: Literal["fail-fast", "finish-open-branches", "ignore"] = (
        Field(
            title="Parallel Branch Policy",
            description="How the process handles a failure in one parallel branch.",
            default="finish-open-branches",
            json_schema_extra={
                "group": "Parallel Execution",
                "editable": True,
                "visible": True,
            },
        )
    )

    as_pump_volume: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml")] = Field(
        title="AS Pump Volume",
        description="Autosampler pump volume used by the first branch.",
        default=ChemUnitQuantity("10 ml"),
        json_schema_extra={
            "group": "Device Commands",
            "editable": True,
            "visible": True,
            "unit": "ml",
        },
    )

    as_pump_rate: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml / min")] = (
        Field(
            title="AS Pump Rate",
            description="Autosampler pump infusion or withdrawal rate.",
            default=ChemUnitQuantity("50 ml / min"),
            json_schema_extra={
                "group": "Device Commands",
                "editable": True,
                "visible": True,
                "unit": "ml / min",
            },
        )
    )

    quench_volume: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml")] = Field(
        title="Quench Volume",
        description="Quench stream volume used by the second branch.",
        default=ChemUnitQuantity("5 ml"),
        json_schema_extra={
            "group": "Device Commands",
            "editable": True,
            "visible": True,
            "unit": "ml",
        },
    )

    quench_rate: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml / min")] = Field(
        title="Quench Rate",
        description="Quench pump infusion or withdrawal rate.",
        default=ChemUnitQuantity("25 ml / min"),
        json_schema_extra={
            "group": "Device Commands",
            "editable": True,
            "visible": True,
            "unit": "ml / min",
        },
    )

    reagent_volume: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml")] = Field(
        title="Reagent Volume",
        description="Reagent stream volume used by the third branch.",
        default=ChemUnitQuantity("5 ml"),
        json_schema_extra={
            "group": "Device Commands",
            "editable": True,
            "visible": True,
            "unit": "ml",
        },
    )

    reagent_rate: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml / min")] = (
        Field(
            title="Reagent Rate",
            description="Reagent pump infusion or withdrawal rate.",
            default=ChemUnitQuantity("20 ml / min"),
            json_schema_extra={
                "group": "Device Commands",
                "editable": True,
                "visible": True,
                "unit": "ml / min",
            },
        )
    )

    wait_for_feedback: bool = Field(
        title="Wait For Feedback",
        description="Wait for configured device feedback before completing a branch.",
        default=True,
        json_schema_extra={
            "group": "Automation",
            "editable": True,
            "visible": True,
        },
    )

    enable_relay: bool = Field(
        title="Enable Relay",
        description="Enable relay commands during the synchronized branch step.",
        default=True,
        json_schema_extra={
            "group": "Automation",
            "editable": True,
            "visible": True,
        },
    )

    collect_branch_logs: bool = Field(
        title="Collect Branch Logs",
        description="Keep separate log snippets for each parallel branch.",
        default=True,
        json_schema_extra={
            "group": "Parallel Execution",
            "editable": True,
            "visible": True,
        },
    )


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
                position=(200.0, 300.0),
            ).model_dump(exclude_none=True),
            block_tag="start",
        )

        graph.add_node(
            "end",
            **WorkflowNodeSpec(
                node_id="end",
                method="finish",
                position=(1150.0, 300.0),
            ).model_dump(exclude_none=True),
            block_tag="end",
        )

        graph.add_node(
            "script_1",
            **WorkflowNodeSpec(
                node_id="script_1",
                method="script_1",
                position=(450.0, 100.0),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "script_2",
            **WorkflowNodeSpec(
                node_id="script_2",
                method="script_2",
                position=(450.0, 300.0),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "script_3",
            **WorkflowNodeSpec(
                node_id="script_3",
                method="script_3",
                position=(450.0, 500.0),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "script_4",
            **WorkflowNodeSpec(
                node_id="script_4",
                method="script_4",
                position=(800.0, 300.0),
            ).model_dump(exclude_none=True),
            block_tag="script",
        )

        graph.add_node(
            "loop_1",
            **WorkflowNodeSpec(
                node_id="loop_1",
                method="loop_1",
                position=(975.0, 300.0),
            ).model_dump(exclude_none=True),
            block_tag="loop",
        )

        graph.add_edge(
            "start",
            "script_1",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "start",
            "script_2",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "start",
            "script_3",
            **WorkflowEdgeSpec(
                condition=True,
            ).model_dump(exclude_none=True),
        )

        graph.add_edge(
            "script_1",
            "script_4",
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
            "script_3",
            "script_4",
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
            "loop_1",
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
        ctx.report_progress(
            0,
            f"AS branch: infusing {self.config.as_pump_volume} at {self.config.as_pump_rate}.",
        )
        ctx.report_progress(50, "AS branch: infusion in progress.")
        ctx.report_progress(100, "Script 1 ran.")
        return True

    def script_2(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(
            0,
            f"Quench branch: dosing {self.config.quench_volume} at {self.config.quench_rate}.",
        )
        ctx.report_progress(50, "Quench branch: dosing in progress.")
        ctx.report_progress(100, "Script 2 ran.")
        return True

    def loop_1(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(
            0, f"Retrying up to {self.config.retry_count} time(s) if needed."
        )
        ctx.report_progress(100, "Loop 1 ran.")
        return True

    def script_3(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(
            0,
            f"Reagent branch: dosing {self.config.reagent_volume} at {self.config.reagent_rate}.",
        )
        ctx.report_progress(50, "Reagent branch: dosing in progress.")
        ctx.report_progress(100, "Script 3 ran.")
        return True

    def script_4(self, ctx: NodeExecutionContext) -> bool:
        ctx.report_progress(0, "Joining parallel branches.")
        if self.config.wait_for_feedback:
            ctx.report_progress(40, "Waiting for device feedback before continuing.")
        if self.config.enable_relay:
            ctx.report_progress(70, "Triggering synchronized relay step.")
        ctx.report_progress(100, "Script 4 ran.")
        return True
