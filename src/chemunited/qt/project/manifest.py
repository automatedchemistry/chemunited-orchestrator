from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ProjectManifest:
    name: str
    chemunited_version: str
    created: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    last_modified: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    description: str = ""
    processes_order: list[str] = field(default_factory=list)

    # ── I/O ───────────────────────────────────────────────

    def save(self, working_dir: Path) -> None:
        self.last_modified = datetime.now(timezone.utc).isoformat()
        path = working_dir / "manifest.json"
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, working_dir: Path) -> ProjectManifest:
        path = working_dir / "manifest.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**data)

    @classmethod
    def exists(cls, working_dir: Path) -> bool:
        return (working_dir / "manifest.json").exists()