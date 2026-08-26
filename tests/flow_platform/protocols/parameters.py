from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProcessConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    wait_time: float = Field(
        default=60.0, ge=0.0, description="Seconds to hold the simulation open."
    )
