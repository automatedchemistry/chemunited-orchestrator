"""The project's .gitignore.

ChemUnited doesn't version projects; users who want history version the
project folder themselves, with git. Every project still gets a .gitignore,
so such a repository leaves out what belongs to one machine or one run.
"""

from __future__ import annotations

from pathlib import Path

_GITIGNORE = """\
# Python
__pycache__/
*.pyc
*.pyo

# ChemUnited session
.chemunited_session
.chemunited_lock

# Connectivity is machine-specific
connectivity/associations.json

# Execution logs are local run outputs
log/

# The work-server's lock while a run is active
run.lock

# Simulation results are local run outputs
simulations/

# OS
.DS_Store
Thumbs.db
"""

# Rules added to an existing project's .gitignore when missing.
_LOCAL_OUTPUT_RULES = (
    ("# Execution logs are local run outputs", "log/"),
    ("# Simulation results are local run outputs", "simulations/"),
    ("# The work-server's lock while a run is active", "run.lock"),
)


def ensure_gitignore(working_dir: Path) -> None:
    gitignore = working_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(_GITIGNORE, encoding="utf-8")
        return

    content = gitignore.read_text(encoding="utf-8")
    lines = content.splitlines()
    missing = [rule for rule in _LOCAL_OUTPUT_RULES if rule[1] not in lines]
    if not missing:
        return
    if content and not content.endswith("\n"):
        content += "\n"
    for comment, pattern in missing:
        content += f"\n{comment}\n{pattern}\n"
    gitignore.write_text(content, encoding="utf-8")
