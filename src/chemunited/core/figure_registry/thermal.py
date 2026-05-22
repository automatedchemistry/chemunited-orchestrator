from dataclasses import dataclass
from typing import override

from chemunited.core.common.enums import ConnectionType
from chemunited.core.components import ComponentMode, NeutralComponentData
from chemunited.core.components.internals import Port


class TemperatureControlMode(ComponentMode): ...


@dataclass
class TemperatureControlData(NeutralComponentData):
    @override
    def internal_structure(self):
        self.port_pairs = [(1,)]
        self.ports_by_number = {
            1: Port(
                number=1,
                component=self.name,
                category=ConnectionType.HEAT,
                relative_position=(25, 0),
            ),
        }
        self.internal_edges = {}
        self.internal_inventories = {}


class PeltierCoolerTemperatureControlMode(ComponentMode): ...


@dataclass
class PeltierCoolerTemperatureControlData(NeutralComponentData):
    @override
    def internal_structure(self):
        self.port_pairs = [(1,)]
        self.ports_by_number = {
            1: Port(
                number=1,
                component=self.name,
                category=ConnectionType.HEAT,
                relative_position=(50, 0),
            )
        }
        self.internal_edges = {}
        self.internal_inventories = {}
