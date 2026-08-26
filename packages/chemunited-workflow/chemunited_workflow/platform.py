"""Platform — read-only registry of device client instances."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from .cancellation import sleep_interruptibly
from .clients import ComponentClient


def _flowchem_configured(assoc: dict[str, Any]) -> bool:
    return bool(assoc.get("component_url", "").strip())


def _sila2_configured(assoc: dict[str, Any]) -> bool:
    return bool(str(assoc.get("sila_host", "")).strip())


def _opcua_configured(assoc: dict[str, Any]) -> bool:
    return bool(str(assoc.get("opcua_endpoint", "")).strip())


def _build_flowchem_client(
    assoc: dict[str, Any], *, server_url: str | None, name: str, common: dict[str, Any]
) -> ComponentClient:
    component_url = assoc["component_url"]
    url = component_url if server_url is None else f"{server_url}/{component_url}"
    return ComponentClient(url=url, component_ui=name, **common)


def _build_sila2_client(
    assoc: dict[str, Any], *, server_url: str | None, name: str, common: dict[str, Any]
):
    from .clients import SilaComponentClient

    return SilaComponentClient(
        host=assoc["sila_host"],
        port=int(assoc["sila_port"]),
        insecure=assoc.get("sila_insecure", True),
        component_ui=name,
        **common,
    )


def _build_opcua_client(
    assoc: dict[str, Any], *, server_url: str | None, name: str, common: dict[str, Any]
):
    from .clients import OpcUaComponentClient

    return OpcUaComponentClient(
        endpoint=assoc["opcua_endpoint"],
        root_node_id=assoc["opcua_node_id"],
        username=assoc.get("opcua_username"),
        password=assoc.get("opcua_password"),
        idle_node_path=assoc.get("opcua_idle_path"),
        idle_value=assoc.get("opcua_idle_value", False),
        component_ui=name,
        **common,
    )


_PROTOCOL_ADAPTERS: dict[
    str, tuple[Callable[[dict[str, Any]], bool], Callable[..., Any]]
] = {
    "flowchem": (_flowchem_configured, _build_flowchem_client),
    "sila2": (_sila2_configured, _build_sila2_client),
    "opcua": (_opcua_configured, _build_opcua_client),
}


class Platform(Mapping[str, ComponentClient]):
    """Read-only registry of device client instances keyed by component name."""

    def __init__(
        self,
        components: dict[str, ComponentClient] | None = None,
        *,
        cancellation_token: threading.Event | None = None,
        pause_event: threading.Event | None = None,
    ) -> None:
        self._registry: dict[str, ComponentClient] = dict(components or {})
        self._cancellation_token = cancellation_token
        self._pause_event = pause_event

    def _wait(self, seconds: float) -> None:
        """Block for ``seconds``, interruptible by run cancellation or pause.

        For a fixed delay unrelated to any specific device (no idle/status
        endpoint to poll) — device commands themselves already wait for the
        device to report idle and don't need this.
        """
        sleep_interruptibly(seconds, self._cancellation_token, self._pause_event)

    def __getitem__(self, name: str) -> ComponentClient:
        try:
            return self._registry[name]
        except KeyError:
            raise KeyError(
                f"Component '{name}' is not registered. "
                f"Available: {list(self._registry)}"
            )

    def __iter__(self):
        return iter(self._registry)

    def __len__(self) -> int:
        return len(self._registry)

    def register(self, name: str, client: ComponentClient) -> None:
        self._registry[name] = client

    @classmethod
    def from_connectivity(
        cls,
        path: Path | str,
        *,
        dry_run: bool = False,
        log_dir: Path | None = None,
        timeout_commands: str = "10 s",
        error_resilient: bool = False,
        cancellation_token: threading.Event | None = None,
        pause_event: threading.Event | None = None,
    ) -> "Platform":
        """Build a Platform from a connectivity/associations.json file.

        Each association may set ``"protocol"`` to ``"flowchem"`` (default),
        ``"sila2"``, or ``"opcua"`` to pick which client class backs it,
        letting one project mix devices across protocols. Entries missing
        their protocol's required fields (e.g. an empty ``component_url`` for
        ``"flowchem"``) are silently skipped — they represent devices that
        exist physically but are not yet mapped.

        When ``log_dir`` is provided each component gets its own JSONL file at
        ``{log_dir}/pool/{component_name}.jsonl`` for live command visibility.

        The top-level ``"server_url"`` is optional. When present, each
        ``"flowchem"`` association's ``component_url`` is treated as relative
        to it (``{server_url}/{component_url}``) — the historical format.
        When absent, every ``"flowchem"`` association's ``component_url``
        must already be a full absolute URL, used as-is.

        Raises
        ------
        OSError
            If the file cannot be read.
        KeyError
            If the file is missing the ``associations`` key.
        ValueError
            If an association names an unsupported ``protocol``.
        json.JSONDecodeError
            If the file is not valid JSON.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        server_url = data.get("server_url")
        if server_url is not None:
            server_url = server_url.rstrip("/")
        common = dict(
            dry_run=dry_run,
            pool_json_log=None,
            timeout_commands=timeout_commands,
            error_resilient=error_resilient,
            cancellation_token=cancellation_token,
            pause_event=pause_event,
        )
        components = {}
        for assoc in data["associations"]:
            protocol = assoc.get("protocol", "flowchem")
            if protocol not in _PROTOCOL_ADAPTERS:
                raise ValueError(
                    f"Unknown protocol {protocol!r} for component {assoc['component']!r}. "
                    f"Supported: {sorted(_PROTOCOL_ADAPTERS)}"
                )
            is_configured, build = _PROTOCOL_ADAPTERS[protocol]
            if not is_configured(assoc):
                continue
            name = assoc["component"]
            pool_json_log = (
                Path(log_dir) / "pool" / f"{name}.jsonl"
                if log_dir is not None
                else None
            )
            components[name] = build(
                assoc,
                server_url=server_url,
                name=name,
                common={**common, "pool_json_log": pool_json_log},
            )
        return cls(
            components, cancellation_token=cancellation_token, pause_event=pause_event
        )

    @classmethod
    def from_project_dir(
        cls,
        project_dir: Path | str,
        *,
        dry_run: bool = False,
        log_dir: Path | None = None,
        timeout_commands: str = "10 s",
        error_resilient: bool = False,
        cancellation_token: threading.Event | None = None,
        pause_event: threading.Event | None = None,
    ) -> "Platform":
        """Shorthand: load from ``{project_dir}/connectivity/associations.json``."""
        return cls.from_connectivity(
            Path(project_dir) / "connectivity" / "associations.json",
            dry_run=dry_run,
            log_dir=log_dir,
            timeout_commands=timeout_commands,
            error_resilient=error_resilient,
            cancellation_token=cancellation_token,
            pause_event=pause_event,
        )
