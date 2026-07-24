from __future__ import annotations

from textwrap import dedent

from loguru import logger

from chemunited.project.storage import load_draw, load_process_classes, save_draw
from chemunited.protocols.workflows.naming import (
    process_class_name,
    process_config_class_name,
)
from chemunited.shared.enums import WindowCategory


def test_save_draw_writes_python_setup(tmp_path):
    save_draw(
        tmp_path,
        {
            "compounds": [
                {
                    "name": "reagent_a",
                    "molecular_weight": 120.0,
                    "cp_liquid": 150.0,
                    "cp_gas": 0.0,
                    "density_liquid": 1050.0,
                    "color_red": 240,
                    "color_green": 157,
                    "color_blue": 0,
                    "color_alpha": 255,
                }
            ],
            "components": [
                {
                    "name": "PumpA",
                    "figure": "HPLCPump",
                    "position": [1.0, 2.0],
                    "angle": 0,
                    "inventory": {
                        "Inventory": {
                            "liquid": {
                                "volume": 2.5e-6,
                                "initial_species": {"water": 0.125},
                            }
                        }
                    },
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
            "reactions": [
                {
                    "target": "ReactorA",
                    "reaction_type": "FirstOrderDecay",
                    "reactant": "reagent_a",
                    "product": "product_b",
                    "rate_constant": 0.3,
                    "phase": "LIQUID",
                    "delta_temperature_per_mol_converted": 2.0,
                }
            ],
        },
    )

    setup_path = tmp_path / "draw" / "setup.py"
    content = setup_path.read_text(encoding="utf-8")

    assert setup_path.exists()
    assert "def build_draw(platform):" in content
    assert "platform.add_compound(" in content
    assert "name='reagent_a'" in content
    assert "molecular_weight=120.0" in content
    assert "cp_gas=0.0" in content
    assert "color_red=240" in content
    assert "color_alpha=255" in content
    assert "platform.add_component(" in content
    assert "position=(1.0, 2.0)" in content
    assert "inventory=" not in content
    assert "initial_species" not in content
    assert "platform.add_connection(" in content
    assert "destiny='ReactorA'" in content
    assert "destiny_port=1" in content
    assert "inflection_points=[[50.0, 25.0]]" in content
    assert "platform.add_reaction(" in content
    assert "reaction_type='FirstOrderDecay'" in content
    assert "rate_constant=0.3" in content
    assert content.rindex("platform.add_compound(") < content.rindex(
        "platform.add_component("
    )
    assert content.rindex("platform.add_component(") < content.rindex(
        "platform.add_connection("
    )
    assert content.rindex("platform.add_connection(") < content.rindex(
        "platform.add_reaction("
    )


def test_load_draw_executes_python_setup(tmp_path):
    setup_path = tmp_path / "draw" / "setup.py"
    setup_path.parent.mkdir(parents=True)
    setup_path.write_text(
        """
def build_draw(platform):
    platform.add_compound(
        name='reagent_a',
        molecular_weight=120.0,
        cp_liquid=150.0,
        cp_gas=0.0,
        density_liquid=1050.0,
        color_red=240,
        color_green=157,
        color_blue=0,
        color_alpha=255,
    )

    platform.add_component(
        name='PumpA',
        figure='HPLCPump',
        position=(0.0, 0.0),
        angle=0,
        inventory={
            'Inventory': {
                'liquid': {
                    'volume': 2.5e-6,
                    'initial_species': {'water': 0.125},
                },
            },
        },
    )

    platform.add_component(
        name='PumpB',
        figure='HPLCPump',
        position=(100.0, 0.0),
        angle=0,
    )

    platform.add_connection(
        origin='PumpA',
        destiny='PumpB',
        origin_port=2,
        destiny_port=1,
        diameter='1 mm',
    )

    platform.add_reaction(
        target='PumpA',
        reaction_type='FirstOrderDecay',
        reactant='reagent_a',
        product='product_b',
        rate_constant=0.3,
        phase='LIQUID',
        delta_temperature_per_mol_converted=2.0,
    )
""".lstrip(),
        encoding="utf-8",
    )

    assert load_draw(tmp_path) == {
        "compounds": [
            {
                "name": "reagent_a",
                "molecular_weight": 120.0,
                "cp_liquid": 150.0,
                "cp_gas": 0.0,
                "density_liquid": 1050.0,
                "color_red": 240,
                "color_green": 157,
                "color_blue": 0,
                "color_alpha": 255,
            }
        ],
        "components": [
            {
                "name": "PumpA",
                "figure": "HPLCPump",
                "position": (0.0, 0.0),
                "angle": 0,
                "inventory": {
                    "Inventory": {
                        "liquid": {
                            "volume": 2.5e-6,
                            "initial_species": {"water": 0.125},
                        }
                    }
                },
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
        "reactions": [
            {
                "target": "PumpA",
                "reaction_type": "FirstOrderDecay",
                "reactant": "reagent_a",
                "product": "product_b",
                "rate_constant": 0.3,
                "phase": "LIQUID",
                "delta_temperature_per_mol_converted": 2.0,
            }
        ],
        "inventory": {},
    }


def test_load_draw_returns_empty_payload_when_setup_is_missing(tmp_path):
    assert load_draw(tmp_path) == {
        "compounds": [],
        "components": [],
        "connections": [],
        "reactions": [],
        "canvas": {},
    }


def test_load_draw_returns_empty_compounds_for_legacy_setup(tmp_path):
    setup_path = tmp_path / "draw" / "setup.py"
    setup_path.parent.mkdir(parents=True)
    setup_path.write_text(
        """
def build_draw(platform):
    platform.add_component(
        name='PumpA',
        figure='HPLCPump',
        position=(0.0, 0.0),
        angle=0,
    )
""".lstrip(),
        encoding="utf-8",
    )

    assert load_draw(tmp_path) == {
        "compounds": [],
        "components": [
            {
                "name": "PumpA",
                "figure": "HPLCPump",
                "position": (0.0, 0.0),
                "angle": 0,
            }
        ],
        "connections": [],
        "reactions": [],
        "inventory": {},
    }


def test_process_class_name_matches_generated_process_scripts():
    assert process_class_name("react") == "CustomProcess"
    assert process_class_name("my_process") == "CustomProcess"
    assert process_config_class_name("ReactRenamed") == "ProcessConfig"


def test_load_process_classes_reloads_external_process_file_changes(tmp_path):
    protocols_dir = tmp_path / "protocols"
    protocols_dir.mkdir()
    (protocols_dir / "__init__.py").write_text(
        dedent(
            """
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
            """
        ).strip()
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


def test_load_process_classes_skips_invalid_process_file(tmp_path):
    records = []
    sink_id = logger.add(
        lambda message: records.append(message.record), level="WARNING"
    )
    protocols_dir = tmp_path / "protocols"
    protocols_dir.mkdir()
    (protocols_dir / "Good.py").write_text(
        _process_content("good_node"), encoding="utf-8"
    )
    (protocols_dir / "Broken.py").write_text(
        "class CustomProcess(\n",
        encoding="utf-8",
    )

    try:
        classes = load_process_classes(tmp_path)
    finally:
        logger.remove(sink_id)

    assert list(classes) == ["Good"]
    assert len(records) == 1
    assert records[0]["extra"]["window"] == WindowCategory.SETUP
    assert "Could not load protocol 'Broken'" in records[0]["message"]
    assert "Broken.py" in records[0]["message"]


def _process_content(node_id: str) -> str:
    return (
        dedent(
            f"""
            from __future__ import annotations

            import networkx as nx
            from pydantic import BaseModel, ConfigDict

            from chemunited_workflow import Process


            class ProcessConfig(BaseModel):
                model_config = ConfigDict(frozen=True)


            class CustomProcess(Process[ProcessConfig]):
                def build_workflow(self) -> nx.DiGraph:
                    graph = nx.DiGraph()
                    graph.add_node({node_id!r})
                    return graph
            """
        ).strip()
        + "\n"
    )
