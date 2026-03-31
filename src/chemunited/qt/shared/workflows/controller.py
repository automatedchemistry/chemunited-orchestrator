from __future__ import annotations

from PyQt5.QtCore import QObject, pyqtSignal

from chemunited.shared.enums.protocols_enum import ProtocolBlock
from chemunited.shared.workflows.process_workflow import (
    BlockData,
    ConnectionData,
    ProcessWorkflow,
)
from chemunited.shared.workflows.workflow_rules import (
    derive_connection_attributes,
    generate_block_name,
    incoming_port_count,
    validate_connection_request,
)


class WorkflowController(QObject):
    model_reset = pyqtSignal()
    block_added = pyqtSignal(str)
    block_updated = pyqtSignal(str)
    block_removed = pyqtSignal(str)
    connection_added = pyqtSignal(str, str)
    connection_updated = pyqtSignal(str, str)
    connection_removed = pyqtSignal(str, str)

    def __init__(
        self, workflow: ProcessWorkflow | None = None, parent: QObject | None = None
    ):
        super().__init__(parent)
        self._workflow = workflow if workflow is not None else ProcessWorkflow()
        self._workflow.ensure_terminal_blocks()

    @property
    def model(self) -> ProcessWorkflow:
        return self._workflow

    def iter_blocks(self):
        return self._workflow.iter_blocks()

    def iter_connections(self):
        return self._workflow.iter_connections()

    def get_block(self, name: str) -> BlockData | None:
        return self._workflow.get_block(name)

    def get_connection(self, start: str, end: str) -> ConnectionData | None:
        return self._workflow.get_connection(start, end)

    def has_connection(self, start: str, end: str) -> bool:
        return self._workflow.has_connection(start, end)

    def incoming_port_count(self, node_name: str) -> int:
        return max(
            1,
            incoming_port_count(
                connection.loopback
                for _, _, connection in self._workflow.incoming_connections(node_name)
            ),
        )

    def rename_process(self, name: str) -> None:
        self._workflow.rename_process(name)
        self.model_reset.emit()

    def add_block(
        self,
        block_tag: ProtocolBlock,
        pos: tuple[float, float],
        ports_numbers: int = 1,
    ) -> BlockData:
        name = generate_block_name(self._workflow.block_names(), block_tag)
        block = self._workflow.add_block(
            name=name,
            pos=pos,
            block_tag=block_tag,
            ports_numbers=ports_numbers,
        )
        self.block_added.emit(block.name)
        return block

    def remove_block(self, name: str) -> None:
        affected_connections = list(
            (
                start,
                end,
            )
            for start, end, _ in self._workflow.iter_connections()
            if name in {start, end}
        )
        affected_targets = {end for start, end in affected_connections if end != name}

        self._workflow.remove_block(name)

        for start, end in affected_connections:
            self.connection_removed.emit(start, end)
        self.block_removed.emit(name)
        for target in affected_targets:
            self.block_updated.emit(target)

    def move_block(self, name: str, pos: tuple[float, float]) -> None:
        self._workflow.move_block(name, pos)
        self.block_updated.emit(name)

    def connect_nodes(self, start_name: str, end_name: str, start_role: str) -> None:
        start_block = self._workflow.get_block(start_name)
        end_block = self._workflow.get_block(end_name)
        if start_block is None or end_block is None:
            return

        validate_connection_request(
            start_name=start_name,
            end_name=end_name,
            start_block_tag=start_block.block_tag,
            start_role=start_role,
            end_role="left",
            existing_connection=self._workflow.has_connection(start_name, end_name),
            has_outgoing_loopback=any(
                connection.loopback
                for _, _, connection in self._workflow.outgoing_connections(start_name)
            ),
        )

        attributes = derive_connection_attributes(start_block.block_tag, start_role)
        self._workflow.add_connection(start_name, end_name, **attributes)
        self.connection_added.emit(start_name, end_name)
        self.block_updated.emit(end_name)

    def remove_connection(self, start: str, end: str) -> None:
        if not self._workflow.has_connection(start, end):
            return
        self._workflow.remove_connection(start, end)
        self.connection_removed.emit(start, end)
        self.block_updated.emit(end)

    def update_connection_geometry(
        self, start: str, end: str, inflection_points: list[tuple[float, float]]
    ) -> None:
        self._workflow.update_connection_geometry(start, end, inflection_points)
        self.connection_updated.emit(start, end)

    def clear_workflow(self) -> None:
        self._workflow.clear()
        self.model_reset.emit()
