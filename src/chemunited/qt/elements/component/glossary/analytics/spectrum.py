import numpy as np
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainterPath

from chemunited_core.common.constant import PATTERN_DIMENSION
from chemunited.qt.elements.component.component_parts import SceneItem
from chemunited.qt.utils.math_functions import multi_peak


class Spectrum(SceneItem):
    def __init__(
        self,
        width: int = PATTERN_DIMENSION,
        height: int | None = None,
        color=Qt.red,
        parent=None,
    ):
        super().__init__(width, height, parent)
        self.color = color

    def paint(self, painter, option, widget=None) -> None:
        # Parameters for the log-normal distribution

        # Create the x-space
        x_list = np.linspace(0, self.width, 100)

        peaks = [
            (int(self.width * np.random.rand(1)[0]), 0.5, 1, 1),  # Peak 1
            (int(self.width * np.random.rand(1)[0]), 0.3, 0.75, 0.8),  # Peak 2
            (int(self.width * np.random.rand(1)[0]), 0.1, 2, 0.5),  # Peak 3
        ]

        y_list = multi_peak(x_list, peaks)
        y_list = 0.7 * self.height * y_list / np.max(y_list)

        path = QPainterPath()
        path.moveTo(0, 0)

        for x, y in zip(x_list, -y_list):
            path.lineTo(float(x), float(y))

        path.lineTo(float(x), 0)

        # Close the path
        path.closeSubpath()

        painter.setPen(self.color)
        painter.setBrush(self.color)

        painter.drawPath(path)
