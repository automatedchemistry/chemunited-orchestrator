"""Abstract process base class for workflow authors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

import networkx as nx
from pydantic import BaseModel

from .compiler import compile_workflow
from .executor import WorkflowExecutor
from .models import WorkflowResult

ConfigT = TypeVar("ConfigT", bound=BaseModel)


class Process(ABC, Generic[ConfigT]):
    """Base class for user-defined workflow processes."""

    def __init__(self, config: ConfigT) -> None:
        self.config = config

    @abstractmethod
    def build_workflow(self) -> nx.DiGraph:
        """Return the authored workflow graph."""

    def run_workflow(self, start_node: str) -> WorkflowResult:
        """Compile and execute the workflow from ``start_node``."""

        compiled = compile_workflow(self.build_workflow())
        executor = WorkflowExecutor(compiled)
        return executor.execute(self, start_node=start_node)
