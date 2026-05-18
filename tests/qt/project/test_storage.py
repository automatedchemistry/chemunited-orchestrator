from __future__ import annotations

from textwrap import dedent

from chemunited.qt.project.storage import load_draw, load_process_classes, save_draw
from chemunited.qt.protocols.workflows.naming import (
    process_class_name,
    process_config_class_name,
)


def test_save_draw_writes_python_setup(tmp_path):
    save_draw(
        tmp_path,
        {
            "components": [
                {
                    "name": "PumpA",
                    "figure": "HPLCPump",
                    "position": [1.0, 2.0],
                    "angle": 0,
                }
            ],
            "connections": [
                {
                    "origin": "PumpA",
                    "destination": "ReactorA",
                    "origin_port": 2,
                    "destination_port": 1,
                    "length": "100 mm",
                    "inflection_points": [[50.0, 25.0]],
                }
            ],
        },
    )

    setup_path = tmp_path / "draw" / "setup.py"
    content = setup_path.read_text(encoding="utf-8")

    assert setup_path.exists()
    assert "def build_draw(platform):" in content
    assert "platform.add_component(" in content
    assert "position=(1.0, 2.0)" in content
    assert "platform.add_connection(" in content
    assert "destiny='ReactorA'" in content
    assert "destiny_port=1" in content
    assert "inflection_points=[[50.0, 25.0]]" in content


def test_load_draw_executes_python_setup(tmp_path):
    setup_path = tmp_path / "draw" / "setup.py"
    setup_path.parent.mkdir(parents=True)
    setup_path.write_text(
        """
def build_draw(platform):
    for name, x in [('PumpA', 0.0), ('PumpB', 100.0)]:
        platform.add_component(
            name=name,
            figure='HPLCPump',
            position=(x, 0.0),
            angle=0,
        )

    platform.add_connection(
        origin='PumpA',
        destiny='PumpB',
        origin_port=2,
        destiny_port=1,
        diameter='1 mm',
    )
""".lstrip(),
        encoding="utf-8",
    )

    assert load_draw(tmp_path) == {
        "components": [
            {
                "name": "PumpA",
                "figure": "HPLCPump",
                "position": (0.0, 0.0),
                "angle": 0,
            },
            {
                "name": "PumpB",
                "figure": "HPLCPump",
                "position": (100.0, 0.0),
                "angle": 0,
            },
        ],
        "connections": [
            {
                "origin": "PumpA",
                "destination": "PumpB",
                "origin_port": 2,
                "destination_port": 1,
                "diameter": "1 mm",
            }
        ],
    }


def test_load_draw_returns_empty_payload_when_setup_is_missing(tmp_path):
    assert load_draw(tmp_path) == {"components": [], "connections": [], "canvas": {}}


def test_process_class_name_matches_generated_process_scripts():
    assert process_class_name("react") == "CustomProcess"
    assert process_class_name("my_process") == "CustomProcess"
    assert process_config_class_name("ReactRenamed") == "ProcessConfig"


def test_load_process_classes_reloads_external_process_file_changes(tmp_path):
    protocols_dir = tmp_path / "protocols"
    protocols_dir.mkdir()
    (protocols_dir / "__init__.py").write_text(
        dedent("""
            from .React import (
                CustomProcess as ReactProcess,
                ProcessConfig as ReactConfig,
            )

            PROCESSES = {
                "React": ReactProcess,
            }

            CONFIGS = {
                "React": ReactConfig,
            }
            """).strip()
        + "\n",
        encoding="utf-8",
    )
    process_path = protocols_dir / "React.py"
    process_path.write_text(_process_content("first_node"), encoding="utf-8")

    first_classes = load_process_classes(tmp_path)
    first_config = first_classes["React"].__orig_bases__[0].__args__[0]
    first_graph = first_classes["React"](first_config()).build_workflow()

    process_path.write_text(_process_content("second_node"), encoding="utf-8")

    second_classes = load_process_classes(tmp_path)
    second_config = second_classes["React"].__orig_bases__[0].__args__[0]
    second_graph = second_classes["React"](second_config()).build_workflow()

    assert "first_node" in first_graph.nodes
    assert "second_node" not in first_graph.nodes
    assert "second_node" in second_graph.nodes
    assert "first_node" not in second_graph.nodes


def _process_content(node_id: str) -> str:
    return (
        dedent(f"""
            from __future__ import annotations

            import networkx as nx
            from pydantic import BaseModel, ConfigDict

            from chemunited.workflow import Process


            class ProcessConfig(BaseModel):
                model_config = ConfigDict(frozen=True)


            class CustomProcess(Process[ProcessConfig]):
                def build_workflow(self) -> nx.DiGraph:
                    graph = nx.DiGraph()
                    graph.add_node({node_id!r})
                    return graph
            """).strip()
        + "\n"
    )
