from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterator

from chemunited_workflow import WorkflowNodeSpec
from networkx import DiGraph
from pydantic import ConfigDict

from chemunited.shared.enums.protocols_enum import ProtocolBlock

from .exceptions import WorkflowRuleViolation
from .workflow_rules import default_terminal_block_specs


class BlockData(WorkflowNodeSpec):
    """GUI-side block model — extends WorkflowNodeSpec with Qt-specific fields."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Override position to be non-optional in the GUI context
    position: tuple[float, float] = (0.0, 0.0)

    # Qt-specific fields (not part of the workflow spec)
    process: str = ""
    file: str | None = None
    block_tag: ProtocolBlock = ProtocolBlock.SCRIPT
    ports_numbers: int = 1
    file_path: Path | None = None
    protected: bool = False

    def to_attrs(self) -> dict[str, Any]:
        return self.model_dump(exclude={"node_id"})

    def to_script(self, indent: str = "        ") -> str:
        spec_keys = set(WorkflowNodeSpec.model_fields)
        kwargs = {k: v for k, v in self.model_dump(include=spec_keys).items()}
        kwarg_lines = "".join(
            f"\n{indent}        {k}={v!r}," for k, v in kwargs.items()
        )
        lines = [
            f"{indent}graph.add_node(",
            f'{indent}    "{self.node_id}",',
            f"{indent}    **WorkflowNodeSpec({kwarg_lines}\n"
            f"{indent}    ).model_dump(exclude_none=True),",
            f"{indent}    block_tag={self.block_tag.value!r},",
        ]
        if self.ports_numbers != 1:
            lines.append(f"{indent}    ports_numbers={self.ports_numbers!r},")
        lines.append(f"{indent})")
        return "\n".join(lines)


@dataclass(slots=True)
class ConnectionData:
    start_role: str = "right"
    condition: bool | None = True
    loopback: bool = False
    trigger_on: bool = False
    label: str = ""
    inflection_points: list[tuple[float, float]] = field(default_factory=list)
    max_iterations: int | None = None

    def copy(self) -> ConnectionData:
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

    def to_script(self, start: str, end: str, indent: str = "        ") -> str:
        if self.loopback:
            lines = [
                f"{indent}graph.add_edge(",
                f'{indent}    "{start}",',
                f'{indent}    "{end}",',
                f"{indent}    loopback=True,",
                f"{indent}    trigger_on={self.trigger_on!r},",
            ]
            if self.label:
                lines.append(f"{indent}    label={self.label!r},")
            if self.inflection_points:
                lines.append(
                    f"{indent}    inflection_points={self.inflection_points!r},"
                )
            if self.max_iterations is not None:
                lines.append(f"{indent}    max_iterations={self.max_iterations!r},")
            lines.append(f"{indent})")
            return "\n".join(lines)

        spec_kwargs = f"\n{indent}        condition={self.condition!r},"
        if self.label:
            spec_kwargs += f"\n{indent}        label={self.label!r},"
        edge_kwargs = ""
        if self.inflection_points:
            edge_kwargs = f"{indent}    inflection_points={self.inflection_points!r},\n"
        return (
            f"{indent}graph.add_edge(\n"
            f'{indent}    "{start}",\n'
            f'{indent}    "{end}",\n'
            f"{indent}    **WorkflowEdgeSpec({spec_kwargs}\n"
            f"{indent}    ).model_dump(exclude_none=True),\n"
            f"{edge_kwargs}"
            f"{indent})"
        )


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
        self._graph.add_node(block.node_id, **{self._NODE_KEY: block})

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
        node_id: str,
        method: str,
        file: str | None = None,
        position: tuple[float, float] = (0.0, 0.0),
        block_tag: ProtocolBlock = ProtocolBlock.SCRIPT,
        ports_numbers: int = 1,
        *,
        file_path: Path | None = None,
        label: str = "",
        description: str = "",
        protected: bool = False,
    ) -> BlockData:
        if self.has_block(node_id):
            raise WorkflowRuleViolation(f"Workflow block '{node_id}' already exists")

        block = BlockData(
            node_id=node_id,
            method=method,
            process=self._process,
            file=file,
            position=(float(position[0]), float(position[1])),
            block_tag=block_tag,
            ports_numbers=max(1, ports_numbers),
            file_path=file_path,
            label=label,
            description=description,
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
        block.position = (float(pos[0]), float(pos[1]))
        return block

    def update_block_metadata(
        self,
        node_id: str,
        label: str,
        description: str,
    ) -> BlockData:
        block = self._require_block(node_id)
        block.label = label.strip() or block.node_id
        block.description = description.strip()
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
            (float(point[0]), float(point[1])) for point in (inflection_points or [])
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
                    node_id=spec.name,
                    method=spec.method,
                    position=spec.pos,
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

    def get_method(self, node: str) -> str:
        return self._require_block(node).method

    def get_description(self, node: str) -> str:
        return self._require_block(node).description or ""

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
