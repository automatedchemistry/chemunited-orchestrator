"""Abstract process base class for workflow authors."""

from __future__ import annotations

import importlib.util
import inspect
import json
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Generic, TypeVar

import networkx as nx
from loguru import logger
from pydantic import BaseModel, ValidationError

from .compiler import compile_workflow
from .executor import WorkflowExecutor
from .models import WorkflowResult
from .orchestrator import Platform
from .terminal import TerminalWorkflowObserver

ConfigT = TypeVar("ConfigT", bound=BaseModel)
ModelT = TypeVar("ModelT", bound=BaseModel)


def _load_class(file_path: Path, class_name: str) -> type:
    module_name = (
        f"_chemunited_process_{file_path.stem}_{abs(hash(file_path.resolve()))}"
    )
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return getattr(module, class_name)


class Process(ABC, Generic[ConfigT]):
    """Base class for user-defined workflow processes."""

    def __init__(self, config: ConfigT) -> None:
        self.config = config
        self.main_parameters: BaseModel | None = None
        self.platform = Platform()
        self.process_index: int = 0

    def set_main_parameters(self, main_parameters: BaseModel) -> None:
        self.main_parameters = main_parameters

    @abstractmethod
    def build_workflow(self) -> nx.DiGraph:
        """Return the authored workflow graph."""

    def load_parameters(self, hystoric_file: str | None = None) -> bool:
        """Load main and process parameters from files next to the process module."""
        process_dir = Path(inspect.getfile(self.__class__)).parent

        main_parameters_path = process_dir / "main_parameters.py"
        if main_parameters_path.exists():
            try:
                main_parameters_class = _load_class(
                    main_parameters_path, "MainParameter"
                )
            except AttributeError:
                logger.error(
                    f"Could not load parameters from {main_parameters_path}: "
                    "MainParameter class not found."
                )
                return False
            except Exception as e:
                logger.error(
                    f"Could not load parameters from {main_parameters_path}: {e}"
                )
                return False

            if main_parameters_class is None:
                logger.error(
                    f"Could not load parameters from {main_parameters_path}: "
                    "MainParameter class not found."
                )
                return False

            try:
                main_parameters = main_parameters_class()
            except ValidationError as e:
                logger.error(
                    f"Could not load parameters from {main_parameters_path}: {e}"
                )
                return False

            if not isinstance(main_parameters, BaseModel):
                logger.error(
                    f"Could not load parameters from {main_parameters_path}: "
                    "MainParameter must inherit from pydantic.BaseModel."
                )
                return False

            self.main_parameters = main_parameters

        hystoric_file_path = (
            process_dir
            / "protocol_hystoric"
            / (hystoric_file if hystoric_file is not None else "parameters.json")
        )
        if not hystoric_file_path.exists():
            # It is not problematic to not have a hystoric file.
            # When the user wants to create a new protocol based on this process,
            # it should be done through the UI.
            return True

        try:
            data = json.loads(hystoric_file_path.read_text(encoding="utf-8"))
            if "main_parameter" in data:
                if self.main_parameters is None:
                    logger.error(
                        f"Could not load parameters from {hystoric_file_path}: "
                        "main_parameters.py was not loaded."
                    )
                    return False
                self.main_parameters = type(self.main_parameters).model_validate(
                    data["main_parameter"]
                )
            key = f"{self.__class__.__name__}_parameters_{self.process_index}"
            if key in data:
                self.config = type(self.config).model_validate(data[key])
            else:
                logger.error(
                    f"Could not load parameters from {hystoric_file_path}: "
                    f"{key} not found."
                )
                return False
        except (OSError, json.JSONDecodeError, ValidationError) as e:
            logger.error(f"Could not load parameters from {hystoric_file_path}: {e}")
            return False
        return True

    def run_workflow(
        self,
        start_node: str,
        terminal_observer: bool = True,
        extra_listeners: list[Callable] | None = None,
        hystoric_file: str | None = None,
        process_index: int = 0,
    ) -> WorkflowResult:
        """Compile and execute the workflow from ``start_node``."""
        self.process_index = process_index
        if not self.load_parameters(hystoric_file=hystoric_file):
            raise RuntimeError("Could not load parameters from process module.")

        graph = self.build_workflow()
        compiled = compile_workflow(graph)

        listeners: list[Callable] = list(extra_listeners or [])

        if terminal_observer:
            terminal = TerminalWorkflowObserver(compiled, refresh_per_second=5)
            listeners.append(terminal.handle_event)
            executor = WorkflowExecutor(compiled, event_listeners=listeners)
            result = executor.execute(self, start_node=start_node)
            terminal.print_execution_report(result, authored_graph=graph)
            return result

        executor = WorkflowExecutor(compiled, event_listeners=listeners)
        return executor.execute(self, start_node=start_node)
