from chemunited.qt.shared.enums import SetupStepMode
from chemunited.qt.shared.graph import GraphCore
from .online_list import OnlineList
from typing import override


class ConnectivityGraphicView(GraphCore):
    MODE = SetupStepMode.CONNECTIVITY

    @override
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(OnlineList.MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    @override
    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(OnlineList.MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    @override
    def dropEvent(self, event):
        if event.mimeData().hasFormat(OnlineList.MIME):
            url_component = event.mimeData().data(OnlineList.MIME).data().decode("utf-8")
            print(url_component)
            event.acceptProposedAction()
        else:
            event.ignore()
