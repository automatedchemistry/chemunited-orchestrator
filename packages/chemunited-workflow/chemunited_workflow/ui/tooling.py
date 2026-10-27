"""``chemunited-workflow ui init`` and ``ui check``: set up and check a project's
``customizations/ui/`` with nothing but Python installed."""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404
import sys
from dataclasses import dataclass, field
from pathlib import Path

from ..api.services.ui_customization import full_override_active, load_ui, ui_dir

TEMPLATES_DIR = Path(__file__).parent / "templates"
TYPES_DIR = Path(__file__).parent / "types"

# Dot-files don't survive packaging, so templates carry them without the dot.
_RENAMES = {"oxlintrc.json": ".oxlintrc.json"}
_LINT_IGNORED = ("dist/**", "vendor/**", "types/**")


def scaffold(project_dir: Path) -> tuple[list[Path], list[Path]]:
    """Create ``customizations/ui/`` from the templates.

    Returns the paths created and the ones kept because they already exist:
    the customer's files are never overwritten. ``types/`` is the exception,
    replaced on every run so it follows the installed chemunited-workflow.
    """
    target_dir = ui_dir(project_dir)
    created: list[Path] = []
    kept: list[Path] = []
    for source in sorted(TEMPLATES_DIR.rglob("*")):
        if not source.is_file() or "__pycache__" in source.parts:
            continue
        relative = source.relative_to(TEMPLATES_DIR)
        target = (
            target_dir / relative.parent / _RENAMES.get(relative.name, relative.name)
        )
        if target.exists():
            kept.append(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        created.append(target)
    if TYPES_DIR.is_dir():
        types_target = target_dir / "types"
        shutil.rmtree(types_target, ignore_errors=True)
        shutil.copytree(TYPES_DIR, types_target)
        created.append(types_target)
    return created, kept


def find_oxlint() -> str | None:
    """The oxlint executable from the ``ui-lint`` extra, if installed."""
    beside_python = Path(sys.executable).parent / (
        "oxlint.exe" if os.name == "nt" else "oxlint"
    )
    if beside_python.is_file():
        return str(beside_python)
    return shutil.which("oxlint")


@dataclass
class CheckReport:
    problems: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def check(project_dir: Path) -> CheckReport:
    """Check ``ui_hook.py`` and the files it names, then lint the ``.vue`` and
    ``.js`` files when oxlint is installed. Compiling the ``.vue`` files needs
    the browser: the dashboard's Customizations page does that part."""
    report = CheckReport()
    if full_override_active(project_dir):
        report.notes.append(
            "customizations/ui/dist/ replaces the whole dashboard, so ui_hook.py is not applied."
        )
    manifest = load_ui(project_dir).manifest
    if not manifest["active"]:
        report.notes.append(
            "No customizations/ui/ui_hook.py. Create one with: chemunited-workflow ui init PROJECT_DIR"
        )
        return report
    for error in manifest["errors"]:
        where = error["source"] + (f":{error['line']}" if error["line"] else "")
        report.problems.append(f"{where}: {error['message']}")
    report.notes.append(
        f"ui_hook.py declares {len(manifest['pages'])} page(s), "
        f"{len(manifest['actions'])} action(s) and {len(manifest['widgets'])} widget(s)."
    )

    oxlint = find_oxlint()
    if oxlint is None:
        report.notes.append(
            'Lint skipped: pip install "chemunited-workflow[ui-lint]" to lint the .vue and .js files.'
        )
    else:
        ignores = [f"--ignore-pattern={pattern}" for pattern in _LINT_IGNORED]
        result = subprocess.run(  # nosec B603
            [oxlint, *ignores, "."],
            cwd=ui_dir(project_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0:
            report.problems.append(f"oxlint:\n{output}")
        else:
            report.notes.append(
                f"oxlint: {output.splitlines()[-1] if output else 'no problems'}"
            )
    report.notes.append(
        "The browser compiles the .vue files: open the dashboard's Customizations page "
        "to see compile errors."
    )
    return report
