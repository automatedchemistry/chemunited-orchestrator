"""Example file for the parameters editor."""

import sys
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, Field
from PyQt5.QtWidgets import QApplication

from chemunited.core.utils import ChemQuantityValidator, ChemUnitQuantity


def some_method():
    ...

# ---------------------------------------------------------------------------
# Comprehensive Pydantic model
# ---------------------------------------------------------------------------


class ProcessParameters(BaseModel):

    campaign_code: str = Field(
        title="Campaign Code",
        description="Unique label used to group this experimental series.",
        default="AURORA_07",
        pattern='^[A-Z0-9_]+$',
        min_length=6,
        max_length=16,
        json_schema_extra={'group': 'Identification', 'editable': True, 'visible': True},
    )

    solvent_recipe: str = Field(
        title="Solvent Recipe",
        description="Short human-readable description of the solvent blend.",
        default="MeCN:H2O 8:2 + 0.1% HCOOH",
        min_length=10,
        max_length=40,
        json_schema_extra={'group': 'Identification', 'editable': True, 'visible': True},
    )

    sample_loop_volume: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml")] = Field(
        title="Sample Loop Volume",
        description="Volume loaded into the injection loop for each screening shot.",
        default=ChemUnitQuantity("2.5 ml"),
        json_schema_extra={'group': 'Flow Setup', 'editable': True, 'visible': True, 'unit': 'ml'},
    )

    residence_time: Annotated[ChemUnitQuantity, ChemQuantityValidator("s")] = Field(
        title="Residence Time",
        description="Target time the reaction slug spends inside the reactor.",
        default=ChemUnitQuantity("90 s"),
        json_schema_extra={'group': 'Flow Setup', 'editable': True, 'visible': True, 'unit': 's'},
    )

    back_pressure: Annotated[ChemUnitQuantity, ChemQuantityValidator("bar")] = Field(
        title="Back Pressure",
        description="Pressure applied to stabilize flow and suppress degassing.",
        default=ChemUnitQuantity("6 bar"),
        json_schema_extra={'group': 'Flow Setup', 'editable': True, 'visible': True, 'unit': 'bar'},
    )

    quench_flow_rate: Annotated[ChemUnitQuantity, ChemQuantityValidator("ml / min")] = Field(
        title="Quench Flow Rate",
        description="Flow rate of the quench stream merged before collection.",
        default=ChemUnitQuantity("0.35 ml / min"),
        json_schema_extra={'group': 'Flow Setup', 'editable': True, 'visible': True, 'unit': 'ml / min'},
    )

    repeat_cycles: int = Field(
        title="Repeat Cycles",
        description="Number of identical injections to run before the wash sequence.",
        default=4,
        ge=1,
        le=12,
        json_schema_extra={'group': 'Automation', 'editable': True, 'visible': True},
    )

    uv_trigger_threshold: float = Field(
        title="UV Trigger Threshold",
        description="Absorbance threshold that marks the front of the slug.",
        default=2.75,
        ge=0.1,
        le=10.0,
        json_schema_extra={'group': 'Automation', 'editable': True, 'visible': True},
    )

    archive_trace_automatically: bool = Field(
        title="Archive Trace Automatically",
        description="Store chromatograms and sensor traces as soon as the run ends.",
        default=True,
        json_schema_extra={'group': 'Automation', 'editable': True, 'visible': True},
    )


def func():
    ...

class AnotherObject:
    a = 1
    b = 2
    c = 3
