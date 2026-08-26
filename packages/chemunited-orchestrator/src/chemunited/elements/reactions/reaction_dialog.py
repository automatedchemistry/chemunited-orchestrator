from __future__ import annotations

from pydantic import ValidationError
from PyQt5.QtWidgets import QFormLayout, QHBoxLayout, QVBoxLayout
from qfluentwidgets import (
    BodyLabel,
    ComboBox,
    DoubleSpinBox,
    PrimaryPushButton,
    PushButton,
)
from qframelesswindow import FramelessDialog

from .model import ReactionDefinition


class ReactionDialog(FramelessDialog):
    """Form for creating a first-order reaction from live project choices."""

    def __init__(
        self,
        target_names: list[str],
        species_names: list[str],
        parent=None,
    ) -> None:
        super().__init__(parent=parent)
        self.setWindowTitle("Add Reaction")
        self.setResizeEnabled(False)
        self._result: ReactionDefinition | None = None

        self.target_combo = ComboBox(self)
        self.target_combo.addItems(target_names)
        self.reactant_combo = ComboBox(self)
        self.reactant_combo.addItems(species_names)
        self.product_combo = ComboBox(self)
        self.product_combo.addItems(species_names)
        if len(species_names) > 1:
            self.product_combo.setCurrentIndex(1)

        self.phase_combo = ComboBox(self)
        self.phase_combo.addItems(["LIQUID", "GAS"])

        self.rate_constant_spin = DoubleSpinBox(self)
        self.rate_constant_spin.setDecimals(9)
        self.rate_constant_spin.setRange(1.0e-9, 1.0e12)
        self.rate_constant_spin.setSingleStep(0.01)
        self.rate_constant_spin.setValue(0.1)
        self.rate_constant_spin.setSuffix(" s⁻¹")

        self.temperature_change_spin = DoubleSpinBox(self)
        self.temperature_change_spin.setDecimals(6)
        self.temperature_change_spin.setRange(-1.0e12, 1.0e12)
        self.temperature_change_spin.setSingleStep(1.0)
        self.temperature_change_spin.setSuffix(" K/mol")

        form = QFormLayout()
        form.setSpacing(12)
        form.addRow("Reaction type", BodyLabel("FirstOrderDecay", self))
        form.addRow("Target component", self.target_combo)
        form.addRow("Reactant", self.reactant_combo)
        form.addRow("Product", self.product_combo)
        form.addRow("Rate constant", self.rate_constant_spin)
        form.addRow("Phase", self.phase_combo)
        form.addRow("Temperature change", self.temperature_change_spin)

        self.error_label = BodyLabel("", self)
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #c42b1c;")
        self.error_label.hide()

        cancel_button = PushButton("Cancel", self)
        cancel_button.clicked.connect(self.reject)  # type: ignore[attr-defined]
        save_button = PrimaryPushButton("Add reaction", self)
        save_button.clicked.connect(self._save)  # type: ignore[attr-defined]
        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(cancel_button)
        actions.addWidget(save_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, self.titleBar.height() + 20, 24, 20)
        layout.setSpacing(14)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addLayout(actions)
        self.setMinimumWidth(520)

    def _save(self) -> None:
        try:
            self._result = ReactionDefinition(
                target=self.target_combo.currentText(),
                reactant=self.reactant_combo.currentText(),
                product=self.product_combo.currentText(),
                rate_constant=self.rate_constant_spin.value(),
                phase=self.phase_combo.currentText(),
                delta_temperature_per_mol_converted=(
                    self.temperature_change_spin.value()
                ),
            )
        except ValidationError as exc:
            message = exc.errors()[0].get("msg", "Invalid reaction definition.")
            self.error_label.setText(str(message))
            self.error_label.show()
            return
        self.accept()

    def get_result_instance(self) -> ReactionDefinition | None:
        return self._result
