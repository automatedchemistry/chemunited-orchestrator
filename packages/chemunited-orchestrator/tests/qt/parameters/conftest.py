from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

PROCESS_SOURCE = """
from pydantic import BaseModel, Field

from ._lib.limits import MAX_CYCLES


class ProcessConfig(BaseModel):
    cycles: int = Field(
        default=2,
        title="Cycles",
        description="Number of cycles.",
        ge=1,
        le=MAX_CYCLES,
        json_schema_extra={"group": "General", "editable": True, "visible": True},
    )


class CustomProcess:
    pass
"""


@pytest.fixture
def process_with_relative_imports(tmp_path: Path) -> Path:
    """A process file that takes a value from a helper package, as AGA's do."""
    protocols = tmp_path / "protocols"
    (protocols / "_lib").mkdir(parents=True)
    (protocols / "__init__.py").write_text("", encoding="utf-8")
    (protocols / "_lib" / "__init__.py").write_text("", encoding="utf-8")
    (protocols / "_lib" / "limits.py").write_text("MAX_CYCLES = 9\n", encoding="utf-8")
    path = protocols / "Wash.py"
    path.write_text(dedent(PROCESS_SOURCE).lstrip(), encoding="utf-8")
    return path
