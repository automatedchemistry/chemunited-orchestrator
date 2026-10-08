import pytest

from chemunited.elements.component.component_factory import create_component


class _RecordingPainter:
    def __init__(self):
        self.rect = None

    def setPen(self, *_):
        pass

    def setBrush(self, *_):
        pass

    def drawRoundedRect(self, rect, *_):
        self.rect = rect


def _drawn_fill(item) -> float:
    painter = _RecordingPainter()
    item.paint(painter, None)
    return painter.rect.height() / item.height


def test_each_well_is_drawn_from_its_own_inventory(qapp):
    tray = create_component(
        figure="Vial",
        name="Tray",
        position=(0.0, 0.0),
        row=2,
        column=3,
        capacity="1 ml",
    )
    inventories = tray.graph.inf.internal_inventories
    inventories["A1"].liq_content.volume = 0.6e-6
    inventories["B1"].liq_content.volume = 0.4e-6

    fills = {key: _drawn_fill(item) for key, item in tray.graph.vial_content.items()}

    assert fills["A1"] == pytest.approx(0.6, abs=0.05)
    assert fills["B1"] == pytest.approx(0.4, abs=0.05)
    assert fills["A2"] == 0.0
