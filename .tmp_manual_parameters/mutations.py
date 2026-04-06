from pydantic import BaseModel, Field


def helper():
    return "helper"


class ProcessParameters(BaseModel):

    run_label: str = Field(
        title="Run Label",
        description="Short run name.",
        default="run-01",
        min_length=3,
        max_length=20,
        json_schema_extra={'group': 'General', 'editable': True, 'visible': True},
    )

    cycles: int = Field(
        title="Cycles",
        description="Number of cycles.",
        default=2,
        ge=1,
        le=9,
        json_schema_extra={'group': 'General', 'editable': True, 'visible': True},
    )

    x: str = Field(
        title="",
        description="",
        default="",
        min_length=1,
        max_length=50,
        json_schema_extra={'group': 'General', 'editable': True, 'visible': True},
    )

    def update(self):
        ...


class Tail:
    value = 1
