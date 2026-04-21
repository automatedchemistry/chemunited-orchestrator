from types import SimpleNamespace

from chemunited.qt.orchestrator.core import OrchestratorCore


def test_format_infor_flyout_content_without_exception():
    record = {"message": "Everything is fine.", "exception": None}

    content = OrchestratorCore._format_infor_flyout_content(record)

    assert content == "Everything is fine."


def test_format_infor_flyout_content_with_exception_summary():
    record = {
        "message": "Could not open project 'demo.chemunited': invalid manifest",
        "exception": SimpleNamespace(
            type=ValueError,
            value=ValueError("invalid manifest"),
        ),
    }

    content = OrchestratorCore._format_infor_flyout_content(record)

    assert "Could not open project 'demo.chemunited': invalid manifest" in content
    assert "See Detailed Records for traceback." in content
    assert "ValueError: invalid manifest" not in content


def test_format_infor_flyout_content_adds_missing_exception_summary():
    record = {
        "message": "Could not restore protocol.",
        "exception": SimpleNamespace(
            type=RuntimeError,
            value=RuntimeError("workflow graph is invalid"),
        ),
    }

    content = OrchestratorCore._format_infor_flyout_content(record)

    assert "Could not restore protocol." in content
    assert "RuntimeError: workflow graph is invalid" in content
    assert content.endswith("See Detailed Records for traceback.")
