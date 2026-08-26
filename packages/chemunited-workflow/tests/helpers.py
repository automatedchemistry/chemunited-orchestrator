"""Shared test utilities and source-code templates."""

from pathlib import Path


MINIMAL_PROCESS_SRC = """
from typing import Annotated

from pydantic import BaseModel
from chemunited_quantities import ChemQuantityValidator, ChemUnitQuantity
from chemunited_workflow import Process, NodeExecutionContext, WorkflowEdgeSpec, WorkflowNodeSpec
import networkx as nx

class MyConfig(BaseModel):
    value: float = 1.0
    flow_rate: Annotated[
        ChemUnitQuantity,
        ChemQuantityValidator("ml/min"),
    ] = ChemUnitQuantity("0.1 ml/min")

class MyProcess(Process):
    def build_workflow(self):
        g = nx.DiGraph()
        g.add_node("start",  **WorkflowNodeSpec(node_id="start",  method="start",  label="Start").model_dump(exclude_none=True))
        g.add_node("finish", **WorkflowNodeSpec(node_id="finish", method="finish", label="Finish").model_dump(exclude_none=True))
        g.add_edge("start", "finish", **WorkflowEdgeSpec(condition=True).model_dump(exclude_none=True))
        return g
    def start(self, ctx: NodeExecutionContext) -> bool:
        return True
    def finish(self, ctx: NodeExecutionContext) -> bool:
        return True
"""

MAIN_PARAMETERS_SRC = """
from typing import Annotated

from chemunited_quantities import ChemQuantityValidator, ChemUnitQuantity
from pydantic import BaseModel

class MainParameter(BaseModel):
    reagent_volume_ml: float = 5.0
    target_temperature_c: float = 25.0
    main_flow_rate: Annotated[
        ChemUnitQuantity,
        ChemQuantityValidator("ml/min"),
    ] = ChemUnitQuantity("0.2 ml/min")
"""


def write_source(directory: Path, filename: str, source: str) -> Path:
    """Write Python source text to *directory/filename* and return the path."""
    path = directory / filename
    path.write_text(source, encoding="utf-8")
    return path


def make_project_tree(tmp_path: Path) -> dict:
    """Create the standard project directory layout inside *tmp_path*.

    Returns a dict with keys ``process_dir``, ``historic_dir``,
    ``connectivity_dir``, ``log_dir``, and ``protocols_dir`` pointing to the
    created directories.
    """
    process_dir = tmp_path / "processes"
    historic_dir = tmp_path / "protocols_historic"
    connectivity_dir = tmp_path / "connectivity"
    log_dir = tmp_path / "log"
    protocols_dir = tmp_path / "protocols"
    for d in (process_dir, historic_dir, connectivity_dir, log_dir, protocols_dir):
        d.mkdir()
    write_source(process_dir, "my_process.py", MINIMAL_PROCESS_SRC)
    write_source(process_dir, "main_parameters.py", MAIN_PARAMETERS_SRC)
    return {
        "process_dir": process_dir,
        "historic_dir": historic_dir,
        "connectivity_dir": connectivity_dir,
        "log_dir": log_dir,
        "protocols_dir": protocols_dir,
    }
