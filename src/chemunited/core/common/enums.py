from enum import StrEnum


class GroupParameterCategory(StrEnum):
    GENERAL = "General"
    PROPERTY = "Property"
    STATUS = "Status"


class ConnectionType(StrEnum):
    HYDRAULIC = "hydraulic"
    MOVEMENT = "movement"
    HEAT = "heat"
    ELECTRONIC = "electronic"


class PhaseKind(StrEnum):
    LIQUID = "liquid"
    GAS = "gas"
