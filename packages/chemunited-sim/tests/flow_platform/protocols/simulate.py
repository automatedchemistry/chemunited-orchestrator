from __future__ import annotations

import networkx as nx
from chemunited_workflow import (
    NodeExecutionContext,
    Process,
    WorkflowEdgeSpec,
    WorkflowNodeSpec,
)
from pydantic import BaseModel, ConfigDict, Field


class ProcessConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    wait_time: float = Field(default=60.0, ge=0.0)


class CustomProcess(Process[ProcessConfig]):

    def build_workflow(self) -> nx.DiGraph:
        G = nx.DiGraph()

        G.add_node(
            "start",
            **WorkflowNodeSpec(node_id="start", method="start").model_dump(
                exclude_none=True
            ),
            block_tag="start",
        )
        G.add_node(
            "wait",
            **WorkflowNodeSpec(node_id="wait", method="wait").model_dump(
                exclude_none=True
            ),
            block_tag="script",
        )
        G.add_node(
            "end",
            **WorkflowNodeSpec(node_id="end", method="finish").model_dump(
                exclude_none=True
            ),
            block_tag="end",
        )

        G.add_edge(
            "start",
            "wait",
            **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
        )
        G.add_edge(
            "wait",
            "end",
            **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
        )

        return G

    def start(self, ctx: NodeExecutionContext) -> bool:
        ctx.runtime.status_message = "Simulation running."
        return True

    def wait(self, _ctx: NodeExecutionContext) -> bool:
        self.platform["divertvalve"].put("open")
        self.platform._wait(20.0)
        self.platform["chiller"].put("temperature", temp="330 K")
        self.platform["liquidpump"].put("infuse", rate="3 ml/min", volume="9 ml")
        self.platform["pump"].put("infuse", rate="0.3 ml/min", volume="1 ml")
        self.platform["mfc"].put("set-flow-rate", flowrate="1 ml/min")
        self.platform["divertvalve"].put("open")
        self.platform._wait(20.0)
        remaining = max(0.0, self.config.wait_time - 20.0)
        self.platform["divertvalve"].put("close")
        self.platform._wait(remaining)
        return True

    def finish(self, ctx: NodeExecutionContext) -> bool:
        ctx.runtime.status_message = "Simulation finished."
        return True
