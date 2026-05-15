from __future__ import annotations

import re

from loguru import logger
from pydantic import BaseModel

from chemunited.workflow.api.fast_api import RunController
from chemunited.workflow.orchestrator import Platform


class Params(BaseModel):
    pass


def test_execution_log_uses_protocol_history_stem(tmp_path):
    controller = RunController(
        params=Params(),
        processes={},
        platform=Platform(),
        project_dir=tmp_path,
    )

    with controller._execution_log("test_2026-03-27T16-18-00.json"):
        logger.info("captured execution message")

    [log_file] = (tmp_path / "log").glob("*.log")
    assert re.fullmatch(
        r"test_2026-03-27T16-18-00__\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}\.log",
        log_file.name,
    )
    assert "captured execution message" in log_file.read_text(encoding="utf-8")
    assert (
        controller._normalize_protocol_hystoric_file("test_2026-03-27T16-18-00")
        == "test_2026-03-27T16-18-00.json"
    )
