from pathlib import Path
from textwrap import dedent

from chemunited.protocols.workflows.process_workflow import BlockData


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
