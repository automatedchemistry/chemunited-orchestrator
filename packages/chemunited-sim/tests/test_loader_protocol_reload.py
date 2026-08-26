from __future__ import annotations

import os
import textwrap
from pathlib import Path

from chemunited_sim.cli.loader import load_project


def _write_project(project_dir: Path, connect: str) -> None:
    draw_dir = project_dir / "draw"
    protocols_dir = project_dir / "protocols"
    draw_dir.mkdir(parents=True, exist_ok=True)
    protocols_dir.mkdir(parents=True, exist_ok=True)

    (draw_dir / "setup.py").write_text(
        textwrap.dedent(
            """
            def build_draw(platform):
                pass
            """
        ),
        encoding="utf-8",
    )
    (protocols_dir / "__init__.py").write_text(
        textwrap.dedent(
            """
            from .Process import CustomProcess as ProcessProcess, ProcessConfig

            PROCESSES = {"Process": ProcessProcess}
            CONFIGS = {"Process": ProcessConfig}
            """
        ),
        encoding="utf-8",
    )
    process_path = protocols_dir / "Process.py"
    process_path.write_text(
        textwrap.dedent(
            f"""
            from __future__ import annotations

            import networkx as nx
            from pydantic import BaseModel, ConfigDict

            from chemunited_workflow import NodeExecutionContext, Process


            class ProcessConfig(BaseModel):
                model_config = ConfigDict(frozen=True)


            class CustomProcess(Process[ProcessConfig]):
                def build_workflow(self) -> nx.DiGraph:
                    return nx.DiGraph()

                def command_2(self, ctx: NodeExecutionContext | None = None) -> bool:
                    self.platform["SixPortDistributionValve"].put(
                        "position",
                        connect="{connect}",
                        disconnect="",
                    )
                    return True
            """
        ),
        encoding="utf-8",
    )


class _RecorderComponent:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def put(self, command: str, **kwargs) -> None:
        self.calls.append((command, kwargs))


def _loaded_connect(project_dir: Path) -> str:
    project = load_project(project_dir)
    recorder = _RecorderComponent()
    process_cls = project.processes["Process"]
    config_cls = project.configs["Process"]
    process = process_cls(config_cls(), platform={"SixPortDistributionValve": recorder})

    assert process.command_2() is True

    command, kwargs = recorder.calls[-1]
    assert command == "position"
    return kwargs["connect"]


def test_load_project_reloads_protocol_submodules(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"

    _write_project(project_dir, "[[0, 3]]")
    assert _loaded_connect(project_dir) == "[[0, 3]]"

    process_path = project_dir / "protocols" / "Process.py"
    later = process_path.stat().st_mtime + 2.0
    _write_project(project_dir, "[[0, 4]]")
    os.utime(process_path, (later, later))

    assert _loaded_connect(project_dir) == "[[0, 4]]"
