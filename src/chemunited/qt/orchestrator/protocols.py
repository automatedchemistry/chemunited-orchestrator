from __future__ import annotations

import re

from loguru import logger
from PyQt5.QtCore import Qt, pyqtSlot
from qfluentwidgets import InfoBar, InfoBarPosition

from chemunited.qt.protocols.workflows import ProcessWorkflow

from .draw import OrchestratorDraw


def is_valid_name(name: str) -> bool:
    """Allow only letters, numbers, underscore, and dash."""
    return re.fullmatch(r"[A-Za-z0-9_-]+", name) is not None


class OrchestratorProtocols(OrchestratorDraw):
    """
    Single writer for the protocols dict.

    Flow for every mutation:
      1. Validate
      2. Write to self.protocols (source of truth)
      3. Drive WorkflowsWidget (visual layer)
      4. Call protocols_widget.sync_list() (list re-renders from dict)

    select_process is read-only — no dict write.
    """

    # ------------------------------------------------------------------
    # Slots — called by ProtocolsWidget signals
    # ------------------------------------------------------------------

    @pyqtSlot(str)
    def add_process(self, name: str) -> None:
        if not is_valid_name(name):
            self._warn_user(
                f"Invalid name {name!r}. Only letters, numbers, _ and - are allowed."
            )
            return
        if name in self.protocols:
            self._warn_user(f"A process named {name!r} already exists.")
            return
        self.protocols[name] = ProcessWorkflow(name)
        self.parent_ref.workflows_protocol.add_process(name, self.protocols[name])
        self.parent_ref.protocols_widget.sync_list()

    @pyqtSlot(str, str)
    def rename_process(self, old_name: str, new_name: str) -> None:
        if not is_valid_name(new_name):
            self._warn_user(
                f"Invalid name {new_name!r}. Only letters, numbers, _ and - are allowed."
            )
            return
        if old_name not in self.protocols:
            logger.error(f"Process not found: {old_name!r}")
            return
        if new_name in self.protocols:
            self._warn_user(f"A process named {new_name!r} already exists.")
            return
        self.protocols[new_name] = self.protocols.pop(old_name)
        self.parent_ref.workflows_protocol.rename_process(old_name, new_name)
        self.parent_ref.protocols_widget.sync_list()

    @pyqtSlot(str)
    def remove_process(self, name: str) -> None:
        if name not in self.protocols:
            logger.error(f"Process not found: {name!r}")
            return
        del self.protocols[name]
        self.parent_ref.workflows_protocol.remove_process(name)
        self.parent_ref.protocols_widget.sync_list()

    @pyqtSlot(str)
    def select_process(self, name: str) -> None:
        self.parent_ref.workflows_protocol.select_process(name)

    @pyqtSlot(str)
    def duplicate_process(self, name: str) -> str:
        new_name = self._generate_process_name(base=name)
        self.protocols[new_name] = self._copy_workflow(self.protocols[name], new_name)
        self.parent_ref.workflows_protocol.add_process(
            new_name, self.protocols[new_name]
        )
        self.parent_ref.protocols_widget.sync_list()
        return new_name

    @pyqtSlot()
    def save_protocols(self) -> None:
        self.parent_ref.save()

    @pyqtSlot(str)
    def access_process_parameters(self, name: str) -> None:
        if name not in self.protocols:
            logger.error(f"Process not found: {name!r}")
            return
        if process := self.parent_ref.workflows_protocol[name]:
            process.access_process_parameters()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def clear_protocols(self) -> None:
        """Remove every process — clears dict, WorkflowsWidget, and the list."""
        self.protocols.clear()
        self.parent_ref.workflows_protocol.clearWorkflows()
        self.parent_ref.protocols_widget.sync_list()

    def _generate_process_name(self, base: str = "Process") -> str:
        """Return a unique name: base → base_1 → base_2 → …"""
        if base not in self.protocols:
            return base
        i = 1
        while f"{base}_{i}" in self.protocols:
            i += 1
        return f"{base}_{i}"

    def _copy_workflow(self, source: ProcessWorkflow, new_name: str) -> ProcessWorkflow:
        """Deep-copy source into a new ProcessWorkflow under new_name."""
        dest = ProcessWorkflow(new_name)
        for _, block in source.iter_blocks():
            if block.protected:
                continue  # terminal blocks already created by ensure_terminal_blocks
            dest.add_block(
                node_id=block.node_id,
                method=block.method,
                file=block.file,
                position=block.position,
                block_tag=block.block_tag,
                ports_numbers=block.ports_numbers,
                file_path=block.file_path,
                label=block.label,
                description=block.description,
                protected=block.protected,
            )
        for start, end, conn in source.iter_connections():
            dest.add_connection(
                start,
                end,
                start_role=conn.start_role,
                condition=conn.condition,
                loopback=conn.loopback,
                trigger_on=conn.trigger_on,
                label=conn.label,
                inflection_points=list(conn.inflection_points),
                max_iterations=conn.max_iterations,
            )
        return dest

    def _warn_user(self, message: str) -> None:
        logger.warning(message)
        InfoBar.warning(
            title="Invalid operation",
            content=message,
            orient=Qt.Horizontal,  # type: ignore[attr-defined]
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self.parent_ref,
        )
