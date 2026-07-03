from chemunited.protocols.workflows.workflow_rules import generate_reuse_name


def test_generate_reuse_name_appends_incrementing_suffix():
    assert generate_reuse_name([], "script_1") == "script_1-1"
    assert generate_reuse_name(["script_1", "script_1-1"], "script_1") == "script_1-2"


def test_generate_reuse_name_bases_off_original_when_source_is_already_a_reuse():
    existing = ["script_1", "script_1-1"]
    assert generate_reuse_name(existing, "script_1-1") == "script_1-2"
