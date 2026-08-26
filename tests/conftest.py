"""Shared fixtures for the chemunited-workflow test suite."""

import pytest
import networkx as nx
from pydantic import BaseModel

from chemunited_workflow import (
    NodeExecutionContext,
    Process,
    WorkflowEdgeSpec,
    WorkflowNodeSpec,
)


class MinimalConfig(BaseModel):
    pass


class MinimalProcess(Process[MinimalConfig]):
    """Trivial two-node workflow used by every test that needs a runnable process."""

    def build_workflow(self) -> nx.DiGraph:
        g: nx.DiGraph = nx.DiGraph()
        g.add_node(
            "start",
            **WorkflowNodeSpec(
                node_id="start", method="start", label="Start"
            ).model_dump(exclude_none=True),
        )
        g.add_node(
            "finish",
            **WorkflowNodeSpec(
                node_id="finish", method="finish", label="Finish"
            ).model_dump(exclude_none=True),
        )
        g.add_edge(
            "start",
            "finish",
            **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True),
        )
        return g

    def start(self, ctx: NodeExecutionContext) -> bool:
        return True

    def finish(self, ctx: NodeExecutionContext) -> bool:
        return True


@pytest.fixture
def minimal_process():
    return MinimalProcess(config=MinimalConfig())
