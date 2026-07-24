from __future__ import annotations

from chemunited_core.compounds import COMPOUNDS
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QWidget
from qfluentwidgets import (
    FluentIcon,
    InfoBar,
    InfoBarPosition,
    ListWidget,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
)

from .model import ReactionDefinition
from .reaction_dialog import ReactionDialog


class ReactionList(QWidget):
    reactions_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(12)
        layout.addWidget(StrongBodyLabel("Configured reactions", self))

        self.list_widget = ListWidget(self)
        self.list_widget.setAlternatingRowColors(True)
        layout.addWidget(self.list_widget, stretch=1)

        self.remove_button = PushButton(FluentIcon.DELETE, "Remove selected", self)
        self.remove_button.setEnabled(False)
        layout.addWidget(self.remove_button, alignment=Qt.AlignLeft)  # type: ignore[arg-type, attr-defined]

        self.add_button = PrimaryPushButton(FluentIcon.ADD, "Add reaction", self)
        layout.addWidget(self.add_button, alignment=Qt.AlignLeft)  # type: ignore[arg-type, attr-defined]

    def _connect_signals(self) -> None:
        self.add_button.clicked.connect(self._open_add_dialog)  # type: ignore[attr-defined]
        self.remove_button.clicked.connect(self.remove_selected_reaction)  # type: ignore[attr-defined]
        self.list_widget.currentRowChanged.connect(  # type: ignore[attr-defined]
            lambda row: self.remove_button.setEnabled(row >= 0)
        )

    def _orchestrator(self):
        return getattr(self.window(), "orchestrator", None)

    def sync(self) -> None:
        selected = self.list_widget.currentRow()
        self.list_widget.clear()
        orchestrator = self._orchestrator()
        reactions = getattr(orchestrator, "reactions", [])
        for reaction in reactions:
            self.list_widget.addItem(self._display_text(reaction))
            item = self.list_widget.item(self.list_widget.count() - 1)
            item.setToolTip(self._tooltip(reaction))
        if 0 <= selected < self.list_widget.count():
            self.list_widget.setCurrentRow(selected)
        self.remove_button.setEnabled(self.list_widget.currentRow() >= 0)

    def visible_reactions(self) -> list[str]:
        return [
            self.list_widget.item(index).text()
            for index in range(self.list_widget.count())
        ]

    def _open_add_dialog(self) -> None:
        orchestrator = self._orchestrator()
        if orchestrator is None:
            return
        targets = orchestrator.reaction_target_names()
        if not targets:
            self._show_warning("Add a vessel with an Inventory or a FlowReactor first.")
            return
        species = list(COMPOUNDS.names)
        if len(species) < 2:
            self._show_warning("At least two compounds are required for a reaction.")
            return

        dialog = ReactionDialog(targets, species, parent=self.window())
        if not dialog.exec_():
            return
        reaction = dialog.get_result_instance()
        if reaction is None:
            return
        if orchestrator.add_reaction(**reaction.model_dump()) is not None:
            self.reactions_changed.emit()

    def remove_selected_reaction(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            self._show_warning("Select a reaction to remove.")
            return
        orchestrator = self._orchestrator()
        if orchestrator is None:
            return
        orchestrator.remove_reaction(row)
        self.reactions_changed.emit()

    @staticmethod
    def _display_text(reaction: ReactionDefinition) -> str:
        return (
            f"{reaction.target}: {reaction.reactant} → {reaction.product} "
            f"({reaction.phase.lower()}, k={reaction.rate_constant:g} s⁻¹)"
        )

    @staticmethod
    def _tooltip(reaction: ReactionDefinition) -> str:
        return (
            f"Type: {reaction.reaction_type}\n"
            f"Target: {reaction.target}\n"
            f"Temperature change: "
            f"{reaction.delta_temperature_per_mol_converted:g} K/mol"
        )

    def _show_warning(self, message: str) -> None:
        InfoBar.warning(
            title="Reactions",
            content=message,
            orient=Qt.Horizontal,  # type: ignore[attr-defined]
            isClosable=True,
            position=InfoBarPosition.TOP,
            duration=3000,
            parent=self.window(),
        )
