"""Abstract process base class for workflow authors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

import networkx as nx
from pydantic import BaseModel

from .compiler import compile_workflow
from .executor import WorkflowExecutor
from .models import WorkflowResult
from .orchestrator import Platform
from .terminal import TerminalWorkflowObserver

ConfigT = TypeVar("ConfigT", bound=BaseModel)


class Process(ABC, Generic[ConfigT]):
    """Base class for user-defined workflow processes."""

    def __init__(self, config: ConfigT) -> None:
        self.config = config
        self.main_parameters: BaseModel | None = None
        self.platform = Platform()

    def set_main_parameters(self, main_parameters: BaseModel) -> None:
        self.main_parameters = main_parameters

    @abstractmethod
    def build_workflow(self) -> nx.DiGraph:
        """Return the authored workflow graph."""

    def run_workflow(
        self, start_node: str, terminal_observer: bool = True
    ) -> WorkflowResult:
        """Compile and execute the workflow from ``start_node``."""
        graph = self.build_workflow()
        compiled = compile_workflow(graph)

        if terminal_observer:
            terminal = TerminalWorkflowObserver(compiled, refresh_per_second=5)
            executor = WorkflowExecutor(
                compiled, event_listeners=[terminal.handle_event]
            )
            result = executor.execute(self, start_node=start_node)
            terminal.print_execution_report(result, authored_graph=graph)
            return result

        executor = WorkflowExecutor(compiled)
        return executor.execute(self, start_node=start_node)
