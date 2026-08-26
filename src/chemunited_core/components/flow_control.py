"""Inline flow-control components: Pump and MassFlowController.

Both use a hub-at-port-1 + junction-edge topology so upstream transport
pockets are staged and re-emitted rather than discarded.

Pump         — forces exactly Q from port 1 to port 2 as a hard flow
               constraint (an ideal flow source): the sim solver excludes the
               junction edge from the resistive network entirely and injects
               Q directly, so the forced flow is exact and correctly-signed
               on every tick regardless of back-pressure. When Q=0 the
               junction is fully closed.

MassFlowController — allows flow up to a setpoint by varying the junction-edge
               resistance each hydraulic step, so it still responds to real
               back-pressure like a controlled valve (unlike Pump, it does
               not force an unconditional flow). When setpoint=0 the edge is
               fully closed.
"""

from dataclasses import dataclass
from typing import Annotated, ClassVar

from chemunited_quantities import (
    ChemQuantityValidator,
    ChemUnitQuantity,
)
from pydantic import Field
from typing_extensions import override

from chemunited_core.common.enums import GroupParameterCategory

from .component import ComponentData, ComponentMode
from .enums import ComponentType, InternalEdgeRole
from .internals import InternalEdge, Port

# ---------------------------------------------------------------------------
# Pump
# ---------------------------------------------------------------------------


class PumpMode(ComponentMode):
    flow_rate: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml/min")] = Field(
        default=ChemUnitQuantity("0 ml/min"),
        title="Flow Rate",
        description="Volumetric flow rate the pump forces through the network.",
        json_schema_extra={
            "group": GroupParameterCategory.STATUS.value,
        },
    )


@dataclass
class PumpData(ComponentData):
    """Two-port inline pump: hub at port 1, forced-flow junction.

    sync_forced_flow() sets the junction edge to force exactly flow_rate from
    port 1 to port 2 as a hard constraint (an ideal flow source) — the sim
    solver excludes the edge's own conductance from the network and injects
    flow_rate directly, so it is correct on every tick regardless of
    back-pressure, matching a real positive-displacement pump whose check
    valves make backflow impossible.  When flow_rate = 0 the junction is
    fully closed.  Transport pockets still flow through the junction edge
    from the upstream hub to the downstream network.
    """

    COMPONENT_TYPE: ClassVar[ComponentType] = ComponentType.ELECTRONIC
    flow_rate: ChemUnitQuantity = ChemUnitQuantity("0 ml/min")

    @property
    def flow_rate_si(self) -> float:
        return float(self.flow_rate.to_base_units().magnitude)  # m³/s

    @override
    def internal_structure(self) -> None:
        self.port_pairs = [(1, 2)]
        self.ports_by_number = {
            1: Port(number=1, component=self.name, is_hub=True),
            2: Port(number=2, component=self.name),
        }
        self.internal_edges = {
            (1, 2): InternalEdge(
                origin_port=1,
                destination_port=2,
                role=InternalEdgeRole.JUNCTION,
            ).close()
        }
        self.internal_inventories = {}

    def sync_forced_flow(self) -> None:
        """Force exactly flow_rate through the junction edge, port 1→2.

        Sets the edge as an ideal flow source: the sim solver excludes its
        conductance from the resistive network and injects flow_rate
        directly, so the forced flow is exact and correctly-signed
        regardless of back-pressure. Closes the junction when flow_rate <= 0.
        """
        edge = self.internal_edges[(1, 2)]
        if self.flow_rate_si <= 0.0:
            edge.close()
            return
        edge.open()
        edge.forced_flow_override = self.flow_rate_si

    def _sync(self) -> None:
        self.sync_forced_flow()

    @override
    def sync_internal_state(self) -> None:
        self._sync()


# ---------------------------------------------------------------------------
# MassFlowController
# ---------------------------------------------------------------------------


class MassFlowControllerMode(ComponentMode):
    flowrate: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml/min")] = Field(
        default=ChemUnitQuantity("0 ml/min"),
        title="Flow Setpoint",
        description="Maximum volumetric flow rate the MFC allows through.",
        json_schema_extra={
            "group": GroupParameterCategory.STATUS.value,
        },
    )


@dataclass
class MassFlowControllerData(ComponentData):
    """Two-port inline mass-flow controller: hub at port 1, active-resistance junction.

    The junction-edge resistance is set each tick by update_resistance(dp) so that
    exactly flowrate passes from port 1 to port 2, regardless of the surrounding
    circuit's pressure differential (mirrors PumpData's active-forcing behavior).
    When flowrate=0 the edge is fully closed.
    """

    COMPONENT_TYPE: ClassVar[ComponentType] = ComponentType.ELECTRONIC
    flowrate: ChemUnitQuantity = ChemUnitQuantity("0 ml/min")

    @property
    def flowrate_si(self) -> float:
        return float(self.flowrate.to_base_units().magnitude)  # m³/s

    @override
    def internal_structure(self) -> None:
        self.port_pairs = [(1, 2)]
        self.ports_by_number = {
            1: Port(number=1, component=self.name, is_hub=True),
            2: Port(number=2, component=self.name),
        }
        edge = InternalEdge(
            origin_port=1,
            destination_port=2,
            role=InternalEdgeRole.JUNCTION,
        )
        if self.flowrate_si <= 0.0:
            edge.close()
        self.internal_edges = {(1, 2): edge}
        self.internal_inventories = {}

    def update_resistance(self, dp: float) -> None:
        """Force exactly flowrate through the junction edge each tick.

        Called once per tick by the sim worker with dp = P_port1 - P_port2.
        R = dp / flowrate is negative when working against back-pressure,
        matching PumpData's active-forcing behavior. Closes only when the
        setpoint itself is 0.
        """
        if self.flowrate_si <= 0.0:
            self.internal_edges[(1, 2)].close()
            return
        r = dp / self.flowrate_si
        self.internal_edges[(1, 2)].open()
        self.internal_edges[(1, 2)].resistance_override = r if r != 0.0 else None
