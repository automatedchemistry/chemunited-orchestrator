from dataclasses import dataclass

from chemunited_quantities import ChemUnitQuantity
from typing_extensions import override

from chemunited_core.components import MassFlowControllerData, PutResult


@dataclass
class MFCComponentData(MassFlowControllerData):

    @override
    def apply(self, command: str, **kwargs) -> PutResult:
        if command == "set-flow-rate":
            self.flowrate = ChemUnitQuantity(kwargs["flowrate"])
            if self.flowrate_si <= 0.0:
                self.internal_edges[(1, 2)].close()
            else:
                self.internal_edges[(1, 2)].open()
        elif command == "stop":
            self.flowrate = ChemUnitQuantity("0 ml/min")
            self.internal_edges[(1, 2)].close()
        return PutResult()
