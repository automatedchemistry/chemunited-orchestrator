from pydantic import BaseModel, Field
from PyQt5.QtWidgets import QApplication

from chemunited.core.utils import ChemQuantityValidator, ChemUnitQuantity
from typing import Annotated

# ---------------------------------------------------------------------------
# Comprehensive Pydantic model — one field per card type
# ---------------------------------------------------------------------------


class ProcessParameters(BaseModel):
    """Full demonstration model; every field exercises a different card type."""

    # ── Identification ──────────────────────────────────────────────────────

    experiment_name: Annotated[
        str,
        Field(
            default="Run-01",
            title="Experiment name",
            description="Human-readable label for this run.",
            min_length=3,
            max_length=12,
            json_schema_extra={"group": "Identification"},
        ),
    ]

    operator: Annotated[
        str,
        Field(
            default="",
            title="Operator",
            description="Name of the person running this experiment.",
            json_schema_extra={"group": "Identification"},
        ),
    ]

    # ── Reactor settings ────────────────────────────────────────────────────

    reactor_volume: Annotated[
        ChemUnitQuantity,
        ChemQuantityValidator("ml"),
        Field(
            default=ChemUnitQuantity("10 ml"),
            title="Reactor volume",
            description="Internal volume of the reactor.",
            json_schema_extra={"group": "Reactor"},
        ),
    ]

    residence_time: Annotated[
        ChemUnitQuantity,
        ChemQuantityValidator("s"),
        Field(
            default=ChemUnitQuantity("60 s"),
            title="Residence time",
            description="Target mean residence time.",
            json_schema_extra={"group": "Reactor"},
        ),
    ]

    back_pressure: Annotated[
        ChemUnitQuantity,
        ChemQuantityValidator("bar"),
        Field(
            default=ChemUnitQuantity("2 bar"),
            title="Back pressure",
            description="Setpoint for the back-pressure regulator.",
            json_schema_extra={"group": "Reactor"},
        ),
    ]

    flow_rate: Annotated[
        ChemUnitQuantity,
        ChemQuantityValidator("ml/min"),
        Field(
            default=ChemUnitQuantity("1 ml/min"),
            title="Flow rate",
            description="Pump flow rate setpoint.",
            json_schema_extra={"group": "Reactor"},
        ),
    ]

    # ── Run parameters ──────────────────────────────────────────────────────

    repetitions: Annotated[
        int,
        Field(
            default=3,
            ge=1,
            le=20,
            title="Repetitions",
            description="How many times to repeat the run.",
            json_schema_extra={"group": "Run parameters"},
        ),
    ]

    sample_interval: Annotated[
        float,
        Field(
            default=0.5,
            ge=0.1,
            le=60.0,
            title="Sample interval (s)",
            description="Time between data-point recordings.",
            json_schema_extra={"group": "Run parameters", "step": 0.1},
        ),
    ]

    collect_samples: Annotated[
        bool,
        Field(
            default=True,
            title="Collect samples",
            description="Enable automatic fraction collection.",
            json_schema_extra={"group": "Run parameters"},
        ),
    ]

    # ── Analysis ────────────────────────────────────────────────────────────

    detection_mode: Annotated[
        str,
        Field(
            default="UV",
            title="Detection mode",
            description="Primary analytical channel.",
            json_schema_extra={
                "group": "Analysis",
                "Options": ["UV", "MS", "NMR", "IR", "Conductivity"],
            },
        ),
    ]

    wavelengths: Annotated[
        list[float],
        Field(
            default_factory=lambda: [254.0, 280.0],
            title="UV wavelengths (nm)",
            description="Wavelengths to record when UV detection is active.",
            json_schema_extra={"group": "Analysis"},
        ),
    ]

    target_compounds: Annotated[
        list[str],
        Field(
            default_factory=lambda: ["product", "starting_material"],
            title="Target compounds",
            description="Compound names expected in the chromatogram.",
            json_schema_extra={"group": "Analysis"},
        ),
    ]

    # ── Notifications ────────────────────────────────────────────────────────

    notify_on_completion: Annotated[
        bool,
        Field(
            default=False,
            title="Notify on completion",
            json_schema_extra={"group": "Notifications"},
        ),
    ]

    # hidden field — card must not appear in the scroll area
    _schema_version: Annotated[
        str,
        Field(
            default="1.0",
            title="Schema version",
            json_schema_extra={"group": "Notifications", "visible": False},
        ),
    ] = "1.0"

    # read-only field — card appears but is greyed out
    instrument_id: Annotated[
        str,
        Field(
            default="SYN-01",
            title="Instrument ID",
            description="Fixed instrument identifier (read-only).",
            json_schema_extra={"group": "Notifications", "editable": False},
        ),
    ]



def main() -> None:
    # Fall back to this file if the real parameters.py does not exist.
    from chemunited.qt.shared.editor.parameters.main import MainParametersEditor
    from PyQt5.QtWidgets import QApplication
    from pathlib import Path
    import sys
    target = Path(__file__)


    app = QApplication(sys.argv)

    win = MainParametersEditor(path=target, class_name="ProcessParameters")
    win.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
