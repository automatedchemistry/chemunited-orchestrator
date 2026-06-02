"""Example file for the parameters editor."""

from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from chemunited_core.utils import ChemQuantityValidator, ChemUnitQuantity


def some_method(): ...


# ---------------------------------------------------------------------------
# Comprehensive Pydantic model
# ---------------------------------------------------------------------------


class MainParameter(BaseModel):

    sample_loop_volume: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml")] = (
        Field(
            title="Sample Loop Volume",
            description="Volume loaded into the injection loop for each screening shot.",
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

    repeat_cycles: int = Field(
        title="Repeat Cycles",
        description="Number of identical injections to run before the wash sequence.",
        default=10,
        ge=1,
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

    archive_trace_automatically: bool = Field(
        title="Archive Trace Automatically here",
        description="Store chromatograms and sensor traces as soon as the run ends.",
        default=True,
        json_schema_extra={"group": "Automation", "editable": True, "visible": True},
    )

    experiment_name: str = Field(
        title="Experiment Name",
        description="Name of the experiment.",
        default="some",
        min_length=0,
        max_length=50,
        json_schema_extra={"group": "General", "editable": True, "visible": True},
    )

    @field_validator("experiment_name")
    @classmethod
    def validate_experiment_name(cls, v):
        if v == "":
            raise ValueError("Experiment name cannot be empty.")
        return v


def func(): ...


class AnotherObject:
    a = 1
    b = 2
    c = 3
