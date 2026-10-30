"""Unit tests for `chemunited-workflow ui init` and `ui check`."""

from __future__ import annotations

import subprocess

import pytest
from click.testing import CliRunner

from chemunited_workflow import cli
from chemunited_workflow.api.services.ui_customization import load_ui
from chemunited_workflow.ui import tooling


@pytest.fixture(autouse=True)
def _no_oxlint(monkeypatch):
    monkeypatch.setattr(tooling, "find_oxlint", lambda: None)


def test_init_creates_a_working_customization(tmp_path):
    created, kept = tooling.scaffold(tmp_path)
    ui = tmp_path / "customizations" / "ui"
    assert kept == []
    for name in (
        "ui_hook.py",
        "pages/HelloPage.vue",
        "theme.css",
        "tsconfig.json",
        ".oxlintrc.json",
        "README.md",
        "types/chemunited.d.ts",
        "types/vue/index.d.ts",
    ):
        assert (ui / name).is_file(), name
    manifest = load_ui(tmp_path).manifest
    assert manifest["errors"] == []
    assert [page["path"] for page in manifest["pages"]] == ["/hello"]


def test_init_keeps_the_customers_files_but_refreshes_types(tmp_path):
    ui = tmp_path / "customizations" / "ui"
    (ui / "types").mkdir(parents=True)
    (ui / "ui_hook.py").write_text("# mine\n", encoding="utf-8")
    (ui / "types" / "stale.d.ts").write_text("", encoding="utf-8")

    _, kept = tooling.scaffold(tmp_path)

    assert ui / "ui_hook.py" in kept
    assert (ui / "ui_hook.py").read_text(encoding="utf-8") == "# mine\n"
    assert not (ui / "types" / "stale.d.ts").exists()
    assert (ui / "types" / "chemunited.d.ts").is_file()


def test_check_without_a_hook_suggests_init(tmp_path):
    report = tooling.check(tmp_path)
    assert report.problems == []
    assert "ui init" in report.notes[0]


def test_check_reports_hook_problems_and_a_skipped_lint(tmp_path):
    tooling.scaffold(tmp_path)
    (tmp_path / "customizations" / "ui" / "pages" / "HelloPage.vue").unlink()
    report = tooling.check(tmp_path)
    assert any("'pages/HelloPage.vue' was not found" in p for p in report.problems)
    assert any("Lint skipped" in note for note in report.notes)


def test_check_runs_oxlint_when_installed(tmp_path, monkeypatch):
    tooling.scaffold(tmp_path)
    monkeypatch.setattr(tooling, "find_oxlint", lambda: "oxlint")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs["cwd"]))
        return subprocess.CompletedProcess(
            args, 1, stdout="pages/A.vue:1:1: error x", stderr=""
        )

    monkeypatch.setattr(tooling.subprocess, "run", fake_run)
    report = tooling.check(tmp_path)

    [(args, cwd)] = calls
    assert args[0] == "oxlint"
    assert args[-1] == "."
    assert "--ignore-pattern=vendor/**" in args
    assert cwd == tmp_path / "customizations" / "ui"
    assert report.problems == ["oxlint:\npages/A.vue:1:1: error x"]


def test_cli_init_then_check(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli.main, ["ui", "init", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "created" in result.output

    result = runner.invoke(cli.main, ["ui", "check", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "No problems found." in result.output


def test_cli_check_exits_1_on_problems(tmp_path):
    ui = tmp_path / "customizations" / "ui"
    ui.mkdir(parents=True)
    (ui / "ui_hook.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    result = CliRunner().invoke(cli.main, ["ui", "check", str(tmp_path)])
    assert result.exit_code == 1
    assert "RuntimeError: boom" in result.output
