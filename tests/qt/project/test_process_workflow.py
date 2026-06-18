from pathlib import Path
from textwrap import dedent

from chemunited.protocols.workflows.process_workflow import BlockData, ProcessWorkflow


def test_script_method_block_extracts_class_method_and_caches(tmp_path: Path):
    script_path = tmp_path / "process_block.py"
    script_path.write_text(
        dedent(
            """
            class DemoProcess:
                def prepare_sample(self, ctx) -> bool:
                    ctx.runtime.status_message = "Prepared"
                    return True
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    block = BlockData(
        node_id="prepare_node",
        method="prepare_sample",
        file=script_path.name,
        file_path=script_path,
    )

    block_source = block.script_method_block

    assert "def prepare_sample(self, ctx) -> bool:" in block_source
    assert 'ctx.runtime.status_message = "Prepared"' in block_source

    script_path.unlink()

    assert block.script_method_block == block_source


def test_script_method_block_returns_empty_for_missing_function(tmp_path: Path):
    script_path = tmp_path / "process_block.py"
    script_path.write_text(
        dedent(
            """
            def different_step(ctx) -> bool:
                return True
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    block = BlockData(
        node_id="prepare_node",
        method="prepare_sample",
        file=script_path.name,
        file_path=script_path,
    )

    assert block.script_method_block == ""


def test_block_script_always_writes_all_workflow_node_spec_fields():
    block = BlockData(
        node_id="script_1",
        method="script_1",
        description="",
        position=(10.0, 20.0),
    )

    source = block.to_script()

    assert "node_id='script_1'," in source
    assert "method='script_1'," in source
    assert "label='script_1'," in source
    assert "description=''," in source
    assert "position=(10.0, 20.0)," in source


def test_update_block_metadata_normalizes_empty_label():
    workflow = ProcessWorkflow("React")
    workflow.add_block(
        node_id="script_1",
        method="script_1",
        position=(10.0, 20.0),
    )

    block = workflow.update_block_metadata(
        "script_1",
        "   ",
        "  Wash the reactor  ",
    )

    assert block.label == "script_1"
    assert block.description == "Wash the reactor"
