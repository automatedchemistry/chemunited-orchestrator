from enum import Enum

from PyQt5.QtGui import QColor
from qfluentwidgets import isDarkTheme


class WorkflowColorStyle(str, Enum):
    CONTOUR_DARK = "#3A3A3A"
    SOLID_DARK = "#525252"
    EVIDENCE_DARK = "#F9F9F9"

    CONTOUR_DARK_BRIGHTER = "#6E6E6E"
    SOLID_DARK_BRIGHTER = "#8A8A8A"

    CONTOUR_LIGHT = "#BFC7D1"
    SOLID_LIGHT = "#F4F7FB"
    EVIDENCE_LIGHT = "#1F2937"

    CONTOUR_LIGHT_DARKER = "#98A2B3"
    SOLID_LIGHT_DARKER = "#D8E0EA"

    @classmethod
    def solid(cls) -> QColor:
        return QColor(cls.SOLID_DARK if isDarkTheme() else cls.SOLID_LIGHT)

    @classmethod
    def contour(cls) -> QColor:
        return QColor(cls.CONTOUR_DARK if isDarkTheme() else cls.CONTOUR_LIGHT)

    @classmethod
    def contour_brighter(cls) -> QColor:
        return QColor(
            cls.CONTOUR_DARK_BRIGHTER if isDarkTheme() else cls.CONTOUR_LIGHT_DARKER
        )

    @classmethod
    def solid_brighter(cls) -> QColor:
        return QColor(
            cls.SOLID_DARK_BRIGHTER if isDarkTheme() else cls.SOLID_LIGHT_DARKER
        )

    @classmethod
    def evidence(cls) -> QColor:
        return QColor(cls.EVIDENCE_DARK if isDarkTheme() else cls.EVIDENCE_LIGHT)
