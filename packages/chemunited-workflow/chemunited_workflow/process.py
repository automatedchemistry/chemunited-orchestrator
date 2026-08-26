"""Abstract process base class for workflow authors."""

from __future__ import annotations

import importlib.util
import inspect
import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Generic, TypeVar

import networkx as nx
from loguru import logger
from pydantic import BaseModel, ValidationError

from .compiler import compile_workflow
from .executor import WorkflowExecutor
from .models import WorkflowResult
from .platform import Platform

ConfigT = TypeVar("ConfigT", bound=BaseModel)


def _load_class(path: Path, class_name: str) -> type:
    """Return *class_name* from the Python source file at *path*.

    Raises
    ------
    ImportError
        If the file cannot be loaded as a module.
    AttributeError
        If *class_name* is not defined in the module.
    """
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot create a module spec from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return getattr(module, class_name)


class Process(ABC, Generic[ConfigT]):
    """Base class for user-defined workflow processes."""

    def __init__(
        self,
        config: ConfigT,
        platform: Platform | None = None,
        process_index: int = 0,
    ) -> None:
        self.config = config
        self.platform = platform if platform is not None else Platform()
        self.process_index = process_index
        self.main_parameters: BaseModel | None = None

    @abstractmethod
    def build_workflow(self) -> nx.DiGraph:
        """Return the authored workflow graph."""

    def run_workflow(self, start_node: str) -> WorkflowResult:
        """Compile and execute the workflow from ``start_node``."""
        compiled = compile_workflow(self.build_workflow())
        executor = WorkflowExecutor(compiled)
        return executor.execute(self, start_node=start_node)

    def load_parameters(self, historic_file: str | None = None) -> bool:
        """Load main and process parameters from files next to the process module.

        Two-phase loading:

        **Phase 1 — MainParameter class**
        Looks for ``main_parameters.py`` in the same directory as the concrete
        process subclass. If found, instantiates ``MainParameter`` with its
        defaults and assigns it to ``self.main_parameters``.

        **Phase 2 — historic JSON**
        Looks for *historic_file* (default: ``"parameters.json"``) in a
        ``protocols_historic/`` directory one level above the process directory.
        If the file exists, it overrides both ``self.main_parameters`` and
        ``self.config`` with validated values from the JSON.

        Returns
        -------
        bool
            ``True`` on success. Also ``True`` when the historic file does not
            exist (that is normal; protocols are created through the UI).
            ``False`` on any class-loading, validation, or I/O error.
        """
        process_path = Path(inspect.getfile(self.__class__))
        process_dir = process_path.parent
        process_name = process_path.stem

        # Phase 1: MainParameter class
        main_parameters_path = process_dir / "main_parameters.py"
        if main_parameters_path.exists():
            try:
                cls = _load_class(main_parameters_path, "MainParameter")
            except AttributeError:
                logger.error(
                    "Could not load parameters from {}: MainParameter class not found.",
                    main_parameters_path,
                )
                return False
            except Exception as exc:
                logger.error(
                    "Could not load parameters from {}: {}", main_parameters_path, exc
                )
                return False

            if not (isinstance(cls, type) and issubclass(cls, BaseModel)):
                logger.error(
                    "Could not load parameters from {}: "
                    "MainParameter must inherit from pydantic.BaseModel.",
                    main_parameters_path,
                )
                return False

            try:
                self.main_parameters = cls()
            except ValidationError as exc:
                logger.error(
                    "Could not load parameters from {}: {}", main_parameters_path, exc
                )
                return False

        # Phase 2: historic JSON
        historic_filename = (
            historic_file if historic_file is not None else "parameters.json"
        )
        historic_file_path = (
            process_dir.parent / "protocols_historic" / historic_filename
        )

        if not historic_file_path.exists():
            return True

        try:
            data = json.loads(historic_file_path.read_text(encoding="utf-8"))

            if "main_parameter" in data:
                if self.main_parameters is None:
                    logger.error(
                        "Could not load parameters from {}: "
                        "main_parameters.py was not loaded.",
                        historic_file_path,
                    )
                    return False
                self.main_parameters = type(self.main_parameters).model_validate(
                    data["main_parameter"]
                )

            key = f"{process_name}_{self.process_index}"
            if key not in data:
                logger.error(
                    "Could not load parameters from {}: key '{}' not found.",
                    historic_file_path,
                    key,
                )
                return False

            self.config = type(self.config).model_validate(data[key])

        except (OSError, json.JSONDecodeError, ValidationError) as exc:
            logger.error(
                "Could not load parameters from {}: {}", historic_file_path, exc
            )
            return False

        return True
