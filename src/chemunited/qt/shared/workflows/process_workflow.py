from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterator

from networkx import DiGraph

from chemunited.shared.enums.protocols_enum import ProtocolBlock
from chemunited.shared.workflows.exceptions import WorkflowRuleViolation
from chemunited.shared.workflows.workflow_rules import default_terminal_block_specs


@dataclass(slots=True)
class BlockData:
    name: str
    process: str
    file: str | None = None
    pos: tuple[float, float] = field(default_factory=lambda: (0.0, 0.0))
    block_tag: ProtocolBlock = ProtocolBlock.SCRIPT
    ports_numbers: int = 1
    file_path: Path | None = None
    call_function: str = ""
    docstring: str = ""
    protected: bool = False

    def to_attrs(self) -> dict[str, Any]:
        return {
            "process": self.process,
            "file": self.file,
            "pos": self.pos,
            "block_tag": self.block_tag,
            "ports_numbers": self.ports_numbers,
            "file_path": self.file_path,
            "call_function": self.call_function,
            "docstring": self.docstring,
            "protected": self.protected,
        }


@dataclass(slots=True)
class ConnectionData:
    start_role: str = "right"
    condition: bool | None = True
    loopback: bool = False
    trigger_on: bool = False
    label: str = ""
    inflection_points: list[tuple[float, float]] = field(default_factory=list)
    max_iterations: int | None = None

    def copy(self) -> "ConnectionData":
        return replace(
            self,
            inflection_points=[
                (point[0], point[1]) for point in self.inflection_points
            ],
        )

    def to_attrs(self) -> dict[str, Any]:
        return {
            "start_role": self.start_role,
            "condition": self.condition,
            "loopback": self.loopback,
            "trigger_on": self.trigger_on,
            "label": self.label,
            "inflection_points": [tuple(point) for point in self.inflection_points],
            "max_iterations": self.max_iterations,
        }


class ProcessWorkflow:
    _NODE_KEY = "block"
    _EDGE_KEY = "connection"

    def __init__(self, process: str = ""):
        self._process = process
        self._graph: DiGraph = DiGraph()
        self.ensure_terminal_blocks()

    @property
    def process(self) -> str:
        return self._process

    @property
    def topology(self) -> DiGraph:
        return self.as_networkx()

    def __contains__(self, item: object) -> bool:
        return isinstance(item, str) and self.has_block(item)

    def __iter__(self) -> Iterator[str]:
        return iter(self._graph.nodes)

    def __len__(self) -> int:
        return self._graph.number_of_nodes()

    def _require_block(self, name: str) -> BlockData:
        block = self.get_block(name)
        if block is None:
            raise WorkflowRuleViolation(f"Workflow block '{name}' does not exist")
        return block

    def _require_connection(self, start: str, end: str) -> ConnectionData:
        connection = self.get_connection(start, end)
        if connection is None:
            raise WorkflowRuleViolation(
                f"Workflow connection '{start} -> {end}' does not exist"
            )
        return connection

    def _store_block(self, block: BlockData) -> None:
        self._graph.add_node(block.name, **{self._NODE_KEY: block})

    def _store_connection(self, start: str, end: str, data: ConnectionData) -> None:
        self._graph.add_edge(start, end, **{self._EDGE_KEY: data})

    def has_block(self, name: str) -> bool:
        return self._graph.has_node(name)

    def has_connection(self, start: str, end: str) -> bool:
        return self._graph.has_edge(start, end)

    def get_block(self, name: str) -> BlockData | None:
        if not self._graph.has_node(name):
            return None
        return self._graph.nodes[name][self._NODE_KEY]

    def get_connection(self, start: str, end: str) -> ConnectionData | None:
        if not self._graph.has_edge(start, end):
            return None
        return self._graph.edges[start, end][self._EDGE_KEY]

    def iter_blocks(self) -> Iterator[tuple[str, BlockData]]:
        for name in self._graph.nodes:
            yield name, self._graph.nodes[name][self._NODE_KEY]

    def iter_connections(self) -> Iterator[tuple[str, str, ConnectionData]]:
        for start, end in self._graph.edges:
            yield start, end, self._graph.edges[start, end][self._EDGE_KEY]

    def incoming_connections(
        self, node: str
    ) -> Iterator[tuple[str, str, ConnectionData]]:
        if not self.has_block(node):
            return iter(())
        return (
            (start, end, self._graph.edges[start, end][self._EDGE_KEY])
            for start, end in self._graph.in_edges(node)
        )

    def outgoing_connections(
        self, node: str
    ) -> Iterator[tuple[str, str, ConnectionData]]:
        if not self.has_block(node):
            return iter(())
        return (
            (start, end, self._graph.edges[start, end][self._EDGE_KEY])
            for start, end in self._graph.out_edges(node)
        )

    def is_protected_block(self, name: str) -> bool:
        block = self.get_block(name)
        return block.protected if block is not None else False

    def block_names(self) -> tuple[str, ...]:
        return tuple(self._graph.nodes)

    def add_block(
        self,
        name: str,
        file: str | None = None,
        pos: tuple[float, float] = (0.0, 0.0),
        block_tag: ProtocolBlock = ProtocolBlock.SCRIPT,
        ports_numbers: int = 1,
        *,
        file_path: Path | None = None,
        call_function: str = "",
        docstring: str = "",
        protected: bool = False,
    ) -> BlockData:
        if self.has_block(name):
            raise WorkflowRuleViolation(f"Workflow block '{name}' already exists")

        block = BlockData(
            name=name,
            process=self._process,
            file=file,
            pos=(float(pos[0]), float(pos[1])),
            block_tag=block_tag,
            ports_numbers=max(1, ports_numbers),
            file_path=file_path,
            call_function=call_function,
            docstring=docstring,
            protected=protected,
        )
        self._store_block(block)
        return block

    def remove_block(self, name: str) -> None:
        block = self._require_block(name)
        if block.protected:
            raise WorkflowRuleViolation(
                f"Workflow block '{name}' is protected and cannot be removed"
            )
        self._graph.remove_node(name)

    def move_block(self, name: str, pos: tuple[float, float]) -> BlockData:
        block = self._require_block(name)
        block.pos = (float(pos[0]), float(pos[1]))
        return block

    def rename_process(self, name: str) -> None:
        self._process = name
        for _, block in self.iter_blocks():
            block.process = name

    def add_connection(
        self,
        start: str,
        end: str,
        *,
        start_role: str = "right",
        condition: bool | None = True,
        loopback: bool = False,
        trigger_on: bool = False,
        label: str = "",
        inflection_points: list[tuple[float, float]] | None = None,
        max_iterations: int | None = None,
        bend_point: tuple[float, float] | None = None,
    ) -> ConnectionData:
        self._require_block(start)
        self._require_block(end)
        if self.has_connection(start, end):
            raise WorkflowRuleViolation(
                f"Workflow connection '{start} -> {end}' already exists"
            )

        normalized_points = [
            (float(point[0]), float(point[1]))
            for point in (inflection_points or [])
        ]
        if bend_point is not None and not normalized_points:
            normalized_points = [(float(bend_point[0]), float(bend_point[1]))]

        connection = ConnectionData(
            start_role=start_role,
            condition=condition,
            loopback=loopback,
            trigger_on=trigger_on,
            label=label,
            inflection_points=normalized_points,
            max_iterations=max_iterations,
        )
        self._store_connection(start, end, connection)
        return connection

    def remove_connection(self, start: str, end: str) -> None:
        self._require_connection(start, end)
        self._graph.remove_edge(start, end)

    def update_connection_geometry(
        self,
        start: str,
        end: str,
        inflection_points: list[tuple[float, float]],
    ) -> ConnectionData:
        connection = self._require_connection(start, end)
        connection.inflection_points = [
            (float(point[0]), float(point[1])) for point in inflection_points
        ]
        return connection

    def ensure_terminal_blocks(self) -> None:
        for spec in default_terminal_block_specs():
            block = self.get_block(spec.name)
            if block is None:
                self.add_block(
                    name=spec.name,
                    pos=spec.pos,
                    block_tag=spec.block_tag,
                    protected=spec.protected,
                )
                continue
            block.process = self._process
            block.block_tag = spec.block_tag
            block.protected = spec.protected

    def clear(self) -> None:
        self._graph.clear()
        self.ensure_terminal_blocks()

    def as_networkx(self) -> DiGraph:
        graph = DiGraph()
        for name, block in self.iter_blocks():
            graph.add_node(name, **block.to_attrs())
        for start, end, connection in self.iter_connections():
            graph.add_edge(start, end, **connection.to_attrs())
        return graph

    def get_file(self, node: str) -> str:
        return self._require_block(node).file or ""

    def get_file_path(self, node: str) -> Path:
        return self._require_block(node).file_path or Path("")

    def get_call_function(self, node: str) -> str:
        return self._require_block(node).call_function

    def get_docstring(self, node: str) -> str:
        return self._require_block(node).docstring

    def export_script_attributes(self, name: str) -> str:
        block = self._require_block(name)
        result = ""
        for key, value in block.to_attrs().items():
            if value is None or key in {"process", "file_path", "protected"}:
                continue
            if isinstance(value, str):
                value = f"'{value}'"
            result += f"{key}={value},"
        return result

    def get_metadata(self, node: str) -> BlockData | None:
        return self.get_block(node)

    def iter_metadata(self) -> Iterator[tuple[str, BlockData]]:
        return self.iter_blocks()
