from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from .reaction_list import ReactionList


class ReactionsWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.reaction_list = ReactionList(self)
        layout.addWidget(self.reaction_list)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.sync()

    def sync(self) -> None:
        self.reaction_list.sync()

    @property
    def list_widget(self):
        return self.reaction_list.list_widget

    def visible_reactions(self) -> list[str]:
        return self.reaction_list.visible_reactions()
