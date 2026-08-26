"""Pytest fixtures shared across the test suite."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

_TMP_ROOT = Path(__file__).resolve().parent.parent / ".tmp_pytest_paths"


def _safe_node_name(nodeid: str) -> str:
    """Convert a pytest node id into a filesystem-friendly directory name."""
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid).strip("._")
    return sanitized or "test"


@pytest.fixture
def tmp_path(request: pytest.FixtureRequest) -> Path:
    """Workspace-local replacement for pytest's tmp_path on this Windows setup.

    Python's tempfile-based directories become inaccessible in this environment,
    while plain Path.mkdir()-created directories behave normally.
    """
    _TMP_ROOT.mkdir(exist_ok=True)
    path = _TMP_ROOT / f"{_safe_node_name(request.node.nodeid)}_{uuid4().hex[:8]}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
