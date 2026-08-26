"""Reaction abstractions and built-in reaction types for chemunited-sim.

``Reaction``             — structural Protocol: any object with a ``step`` method.
``NullReaction``         — no-op, safe default for nodes without chemistry.
``FirstOrderDecay``      — irreversible A → B with first-order kinetics.
``StoichiometricReaction`` — generalised multi-species conversion.
``ReactionsMap``         — registry keyed by inventory node or transport edge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from chemunited_core.common.enums import PhaseKind

from ..common.constant import MIN_REACTION_MOLES
from ..inventory.models import InventoryState


@runtime_checkable
class Reaction(Protocol):
    """Structural interface for a single reaction step.

    Any object that implements ``step(state, dt) -> None`` satisfies this
    Protocol.  Concrete reaction types do not need to inherit from it.

    The method must mutate *state* in-place — it must not return a new state.
    """

    def step(self, state: InventoryState, dt: float) -> None:
        """Apply this reaction to *state* over one time step of *dt* seconds."""
        ...


@runtime_checkable
class PhaseReaction(Protocol):
    """Reaction that can also operate on one transported fluid phase."""

    phase: PhaseKind

    def step_phase(
        self,
        species_moles: dict[str, float],
        temperature: float,
        dt: float,
    ) -> float:
        """Mutate phase composition and return its updated temperature."""
        ...


# Type alias for reactions keyed by inventory-node ID or transport-edge ID.
ReactionsMap = dict[str, list[Reaction]]


# ---------------------------------------------------------------------------
# Built-in reaction types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NullReaction:
    """A no-op reaction.  Used as a safe default and in tests."""

    def step(self, state: InventoryState, dt: float) -> None:  # noqa: ARG002
        pass


@dataclass(frozen=True)
class FirstOrderDecay:
    """Irreversible first-order conversion A → B within one phase.

    Rate law: ``r = rate_constant · n_A``  (mol/s)

    Species moles are updated as::

        Δn_A = −r · dt   (clamped so n_A ≥ 0)
        Δn_B = +r · dt

    Temperature is updated as::

        ΔT = delta_temperature_per_mol_converted · Δn_A_consumed

    **Sign convention for** ``delta_temperature_per_mol_converted``:
    positive means the reaction *raises* vessel temperature (exothermic from
    the vessel's perspective).  This is the opposite sign of the standard
    thermochemical convention for ΔH, but it maps directly onto the
    temperature update ``state.temperature += delta_T_per_mol * delta_n``.
    Set to ``0.0`` (default) for isothermal reactions.

    Attributes
    ----------
    reactant:
        ``species_id`` of the species being consumed.
    product:
        ``species_id`` of the species being produced.
    rate_constant:
        First-order rate constant in 1/s.
    phase:
        ``PhaseKind.LIQUID`` or ``PhaseKind.GAS`` — which phase dict to
        operate on.
    delta_temperature_per_mol_converted:
        Temperature rise per mole of reactant consumed, in K/mol.
        Default ``0.0`` (isothermal).
    """

    reactant: str
    product: str
    rate_constant: float
    phase: PhaseKind
    delta_temperature_per_mol_converted: float = 0.0

    def step(self, state: InventoryState, dt: float) -> None:
        species = (
            state.liq_species_moles
            if self.phase == PhaseKind.LIQUID
            else state.gas_species_moles
        )
        state.temperature = self.step_phase(species, state.temperature, dt)

    def step_phase(
        self,
        species_moles: dict[str, float],
        temperature: float,
        dt: float,
    ) -> float:
        """Apply the kinetic update to one phase composition."""
        species = species_moles
        n_A = species.get(self.reactant, 0.0)
        if n_A < MIN_REACTION_MOLES:
            return temperature

        delta_n = min(self.rate_constant * n_A * dt, n_A)
        if delta_n < MIN_REACTION_MOLES:
            return temperature

        species[self.reactant] = n_A - delta_n
        species[self.product] = species.get(self.product, 0.0) + delta_n
        return temperature + self.delta_temperature_per_mol_converted * delta_n


@dataclass
class StoichiometricReaction:
    """Generalised stoichiometric conversion driven by a controlling species.

    Supports multiple reactants and products with arbitrary stoichiometric
    coefficients.  The reaction rate is first-order in a single *controlling
    species*; all other reactants are consumed proportionally.

    Rate and extent::

        r   = rate_constant · n_controlling        (mol/s)
        dξ  = min(r · dt,  min(n_i / ν_i) for all reactants)

    Species changes::

        Δn_i = −ν_i · dξ   for each reactant i
        Δn_j = +ν_j · dξ   for each product j

    Temperature::

        ΔT = delta_temperature_per_mol_converted · dξ

    See :class:`FirstOrderDecay` for the sign convention on temperature.

    Attributes
    ----------
    reactants:
        ``{species_id: stoichiometric_coefficient}`` — positive coefficients.
    products:
        ``{species_id: stoichiometric_coefficient}`` — positive coefficients.
    controlling_species:
        The ``species_id`` whose moles drive the rate.  Must appear in
        ``reactants``.
    rate_constant:
        First-order rate constant in 1/s.
    phase:
        Phase to operate on.
    delta_temperature_per_mol_converted:
        Temperature change per mol of *controlling species* converted (K/mol).
        Default ``0.0``.
    """

    reactants: dict[str, float]
    products: dict[str, float]
    controlling_species: str
    rate_constant: float
    phase: PhaseKind
    delta_temperature_per_mol_converted: float = 0.0

    def step(self, state: InventoryState, dt: float) -> None:
        species = (
            state.liq_species_moles
            if self.phase == PhaseKind.LIQUID
            else state.gas_species_moles
        )
        state.temperature = self.step_phase(species, state.temperature, dt)

    def step_phase(
        self,
        species_moles: dict[str, float],
        temperature: float,
        dt: float,
    ) -> float:
        """Apply the stoichiometric update to one phase composition."""
        species = species_moles

        n_ctrl = species.get(self.controlling_species, 0.0)
        if n_ctrl < MIN_REACTION_MOLES:
            return temperature

        # Maximum extent limited by available moles of every reactant
        dxi_max = float("inf")
        for sp, coeff in self.reactants.items():
            n = species.get(sp, 0.0)
            if n < MIN_REACTION_MOLES:
                return temperature  # any reactant absent → no reaction this step
            dxi_max = min(dxi_max, n / coeff)

        dxi = min(self.rate_constant * n_ctrl * dt, dxi_max)
        if dxi < MIN_REACTION_MOLES:
            return temperature

        for sp, coeff in self.reactants.items():
            species[sp] = max(species.get(sp, 0.0) - coeff * dxi, 0.0)
        for sp, coeff in self.products.items():
            species[sp] = species.get(sp, 0.0) + coeff * dxi

        return temperature + self.delta_temperature_per_mol_converted * dxi
