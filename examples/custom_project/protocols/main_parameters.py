# Script file of project parameter
# Updated/Created on: 2026-05-06T13:20:38.425134+00:00
# Project name: complete

from typing import Annotated, Literal

from chemunited_quantities import ChemQuantityValidator, ChemUnitQuantity
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MainParameter(BaseModel):
    experiment_name: str = Field(
        title="Experiment Name",
        description="Human-readable name used in run logs and saved protocols.",
        default="dashboard-visualization-demo",
        min_length=1,
        max_length=80,
        json_schema_extra={"group": "General", "editable": True, "visible": True},
    )

    operator_initials: str = Field(
        title="Operator Initials",
        description="Short identifier for the person preparing the run.",
        default="CU",
        min_length=1,
        max_length=8,
        json_schema_extra={"group": "General", "editable": True, "visible": True},
    )

    chemistry_family: Literal["Suzuki", "SNAr", "Amide coupling", "Photoredox"] = Field(
        title="Chemistry Family",
        description="Reaction family used to group protocols in the dashboard.",
        default="Suzuki",
        json_schema_extra={
            "group": "General",
            "editable": True,
            "visible": True,
        },
    )

    priority: Literal["Low", "Normal", "High", "Urgent"] = Field(
        title="Priority",
        description="Scheduling priority for this experiment.",
        default="Normal",
        json_schema_extra={"group": "General", "editable": True, "visible": True},
    )

    sample_loop_volume: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml")] = (
        Field(
            title="Sample Loop Volume",
            description="Volume loaded into the injection loop for each run.",
            default=ChemUnitQuantity("2.5 ml"),
            json_schema_extra={
                "group": "Flow Setup",
                "editable": True,
                "visible": True,
                "unit": "ml",
            },
        )
    )

    residence_time: Annotated[ChemUnitQuantity, ChemQuantityValidator("s")] = Field(
        title="Residence Time",
        description="Target time the reaction slug spends inside the reactor.",
        default=ChemUnitQuantity("90 s"),
        json_schema_extra={
            "group": "Flow Setup",
            "editable": True,
            "visible": True,
            "unit": "s",
        },
    )

    reactor_temperature: Annotated[ChemUnitQuantity, ChemQuantityValidator("degC")] = (
        Field(
            title="Reactor Temperature",
            description="Target reactor temperature for the shared experiment setup.",
            default=ChemUnitQuantity("45 degC"),
            json_schema_extra={
                "group": "Flow Setup",
                "editable": True,
                "visible": True,
                "unit": "degC",
            },
        )
    )

    back_pressure: Annotated[ChemUnitQuantity, ChemQuantityValidator("bar")] = Field(
        title="Back Pressure",
        description="Pressure applied to stabilize flow and suppress degassing.",
        default=ChemUnitQuantity("6 bar"),
        json_schema_extra={
            "group": "Flow Setup",
            "editable": True,
            "visible": True,
            "unit": "bar",
        },
    )

    reagent_flow_rate: Annotated[
        ChemUnitQuantity, ChemQuantityValidator("ml / min")
    ] = Field(
        title="Reagent Flow Rate",
        description="Nominal combined reagent stream flow rate.",
        default=ChemUnitQuantity("0.55 ml / min"),
        json_schema_extra={
            "group": "Flow Setup",
            "editable": True,
            "visible": True,
            "unit": "ml / min",
        },
    )

    quench_flow_rate: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml / min")] = (
        Field(
            title="Quench Flow Rate",
            description="Flow rate of the quench stream merged before collection.",
            default=ChemUnitQuantity("0.35 ml / min"),
            json_schema_extra={
                "group": "Flow Setup",
                "editable": True,
                "visible": True,
                "unit": "ml / min",
            },
        )
    )

    repetition_reactions: int = Field(
        title="Reaction Repetitions",
        description="Number of repeated reaction shots to run.",
        default=4,
        ge=1,
        le=100,
        json_schema_extra={"group": "Automation", "editable": True, "visible": True},
    )

    wash_cycles: int = Field(
        title="Wash Cycles",
        description="Number of wash cycles to perform after the reaction sequence.",
        default=2,
        ge=0,
        le=12,
        json_schema_extra={"group": "Automation", "editable": True, "visible": True},
    )

    uv_trigger_threshold: float = Field(
        title="UV Trigger Threshold",
        description="Absorbance threshold that marks the front of the slug.",
        default=2.75,
        ge=0.1,
        le=10.0,
        json_schema_extra={"group": "Automation", "editable": True, "visible": True},
    )

    collection_window_s: float = Field(
        title="Collection Window",
        description="Fraction collection window after the UV trigger is detected.",
        default=42.0,
        ge=1.0,
        le=600.0,
        json_schema_extra={
            "group": "Collection",
            "editable": True,
            "visible": True,
            "unit": "s",
        },
    )

    archive_traces_automatically: bool = Field(
        title="Archive Traces Automatically",
        description="Store chromatograms and sensor traces when the run ends.",
        default=True,
        json_schema_extra={"group": "Collection", "editable": True, "visible": True},
    )

    enable_priming: bool = Field(
        title="Enable Priming",
        description="Prime configured liquid lines before starting the workflow.",
        default=True,
        json_schema_extra={"group": "Automation", "editable": True, "visible": True},
    )

    dry_run_preview: bool = Field(
        title="Dry Run Preview",
        description="Preview the protocol in the dashboard before physical execution.",
        default=False,
        json_schema_extra={"group": "Automation", "editable": True, "visible": True},
    )

    model_config = ConfigDict(frozen=True)

    @field_validator("experiment_name")
    @classmethod
    def validate_experiment_name(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("Experiment name cannot be empty.")
        return value
