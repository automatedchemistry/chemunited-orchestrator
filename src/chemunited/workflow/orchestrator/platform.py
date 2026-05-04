from __future__ import annotations

import json
from pathlib import Path

from .clients import ComponentClient


class Platform:
    """Platform for component communication."""

    def __init__(self):
        self.components: dict[str, ComponentClient] = {}

    @classmethod
    def from_json(cls, file_path: Path) -> Platform:
        """Get a client for a component."""
        instance = cls()
        with open(file_path, "r") as f:
            data = json.load(f)
        for association in data["associations"]:
            instance.components[association["component"]] = ComponentClient(
                data["server_url"] + "/" + association["device_url"]
            )
        return instance
    
    def __getitem__(self, name: str) -> ComponentClient:
        """Get a client for a component."""
        return self.components[name]
