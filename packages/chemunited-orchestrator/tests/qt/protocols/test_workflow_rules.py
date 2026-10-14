import pytest

from chemunited.protocols.workflows.exceptions import WorkflowRuleViolation
from chemunited.protocols.workflows.workflow_rules import (
    generate_block_name,
    generate_reuse_name,
    validate_connection_request,
)
from chemunited.shared.enums.protocols_enum import ProtocolBlock


def test_generate_reuse_name_appends_incrementing_suffix():
    assert generate_reuse_name([], "script_1") == "script_1-1"
    assert generate_reuse_name(["script_1", "script_1-1"], "script_1") == "script_1-2"


def test_generate_reuse_name_bases_off_original_when_source_is_already_a_reuse():
    existing = ["script_1", "script_1-1"]
    assert generate_reuse_name(existing, "script_1-1") == "script_1-2"


def test_generate_block_name_for_background_block():
    assert generate_block_name([], ProtocolBlock.BACKGROUND) == "background_1"
    assert (
        generate_block_name(["background_1"], ProtocolBlock.BACKGROUND)
        == "background_2"
    )


def test_background_block_cannot_start_a_connection():
    with pytest.raises(WorkflowRuleViolation, match="no outputs"):
        validate_connection_request(
            start_name="background_1",
            end_name="end",
            start_block_tag=ProtocolBlock.BACKGROUND,
            start_role="right",
            end_role="left",
            existing_connection=False,
            has_outgoing_loopback=False,
        )
