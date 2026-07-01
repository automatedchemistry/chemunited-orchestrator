from chemunited.protocols.workflows.process_workflow import BlockData, ProcessWorkflow


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
