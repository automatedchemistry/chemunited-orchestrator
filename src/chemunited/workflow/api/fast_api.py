from __future__ import annotations

import asyncio
import typing
import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter, HTTPException  # type: ignore[import-not-found]
from loguru import logger
from pydantic import BaseModel, ValidationError

from chemunited.workflow.orchestrator import Platform
from chemunited.workflow.process import Process

# ── Shared helpers ─────────────────────────────────────────────────────────────


def _get_config_class(process_cls: type) -> type[BaseModel]:
    for base in getattr(process_cls, "__orig_bases__", []):
        args = typing.get_args(base)
        if args:
            return args[0]
    raise TypeError(f"Cannot determine config class for {process_cls}")


@dataclass
class SequenceEntry:
    slot_id: str
    process_name: str
    config: BaseModel


def _entry_dict(index: int, entry: SequenceEntry) -> dict[str, Any]:
    return {
        "index": index,
        "slot_id": entry.slot_id,
        "process_name": entry.process_name,
        "config": entry.config.model_dump(mode="json"),
    }


# ── Request body models ────────────────────────────────────────────────────────


class AddToSequenceBody(BaseModel):
    process_name: str
    config_overrides: dict[str, Any] = {}


class ReplaceSequenceItem(BaseModel):
    process_name: str
    config_overrides: dict[str, Any] = {}


# ── Controller ─────────────────────────────────────────────────────────────────


class RunController:
    def __init__(
        self, params: BaseModel, processes: dict[str, type], platform: Platform
    ) -> None:
        self._params: BaseModel = params
        self._processes = processes
        self._platform = platform
        self._entries: list[SequenceEntry] = []

        self.router = APIRouter()

        self.router.add_api_route(
            "/main-params",
            self.get_main_params,
            methods=["GET"],
            tags=["Main Parameters"],
            summary="Get current main parameters",
        )
        self.router.add_api_route(
            "/main-params/schema",
            self.get_main_params_schema,
            methods=["GET"],
            tags=["Main Parameters"],
            summary="JSON Schema for main parameters",
        )
        self.router.add_api_route(
            "/main-params",
            self.update_main_params,
            methods=["PATCH"],
            tags=["Main Parameters"],
            summary="Update main parameters",
        )

        self.router.add_api_route(
            "/processes",
            self.list_processes,
            methods=["GET"],
            tags=["Processes"],
            summary="List available process types with their config schemas",
        )

        self.router.add_api_route(
            "/sequence",
            self.get_sequence,
            methods=["GET"],
            tags=["Sequence"],
            summary="Get the current process sequence",
        )
        self.router.add_api_route(
            "/sequence",
            self.add_to_sequence,
            methods=["POST"],
            status_code=201,
            tags=["Sequence"],
            summary="Append a process to the sequence",
        )
        self.router.add_api_route(
            "/sequence",
            self.replace_sequence,
            methods=["PUT"],
            tags=["Sequence"],
            summary="Replace the entire sequence (atomic)",
        )
        self.router.add_api_route(
            "/sequence/{index}",
            self.delete_sequence,
            methods=["DELETE"],
            status_code=204,
            tags=["Sequence"],
            summary="Remove a process from the sequence",
        )
        self.router.add_api_route(
            "/sequence/{index}/config",
            self.patch_config,
            methods=["PATCH"],
            tags=["Sequence"],
            summary="Update config of a process in the sequence",
        )

        self.router.add_api_route(
            "/execute",
            self.execute,
            methods=["POST"],
            tags=["Run"],
            summary="Execute the configured sequence",
        )
        self.router.add_api_route(
            "/stop",
            self.stop,
            methods=["POST"],
            tags=["Run"],
            summary="Stop execution between processes",
        )
        self.router.add_api_route(
            "/status",
            self.status,
            methods=["GET"],
            tags=["Run"],
            summary="Check whether the sequence is running",
        )

        self.is_running: bool = False

    # ── Main parameters ────────────────────────────────────────────────────────

    def get_main_params(self) -> dict[str, Any]:
        """Return the current values of all main parameters.

        **Example response:**
        ```json
        { "target_temperature": 60, "solvent": "ethanol", "concentration": 0.5 }
        ```
        """
        result = self._params.model_dump(mode="json")
        logger.info("GET /main-params → {}", result)
        return result

    def get_main_params_schema(self) -> dict[str, Any]:
        """Return the JSON Schema for the `MainParameter` model.

        Useful for building dynamic forms — lists every field name, type, and default
        without needing to know the class ahead of time.

        **Example response:**
        ```json
        {
          "title": "MainParameter",
          "type": "object",
          "properties": {
            "target_temperature": { "type": "number", "default": 25 },
            "solvent": { "type": "string", "default": "water" }
          }
        }
        ```
        """
        return type(self._params).model_json_schema()

    def update_main_params(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Update one or more main parameter fields.

        Send only the fields you want to change — unmentioned fields keep their current value.
        Returns `409` if a workflow is currently running.

        **Example request:**
        ```json
        { "target_temperature": 80, "solvent": "acetonitrile" }
        ```

        **Example response:**
        ```json
        { "target_temperature": 80, "solvent": "acetonitrile", "concentration": 0.5 }
        ```
        """
        logger.info("PATCH /main-params updates={}", updates)
        if self.is_running:
            logger.warning("PATCH /main-params rejected — workflow is running")
            raise HTTPException(
                status_code=409,
                detail="Cannot update main parameters while workflow is running",
            )
        try:
            self._params = self._params.model_copy(update=updates)
        except ValidationError as e:
            logger.warning("PATCH /main-params validation error: {}", e.errors())
            raise HTTPException(status_code=422, detail=e.errors())
        result = self._params.model_dump(mode="json")
        logger.info("PATCH /main-params → {}", result)
        return result

    # ── Processes ──────────────────────────────────────────────────────────────

    def list_processes(self) -> dict[str, Any]:
        """List all available process types with their config schemas.

        Use this to discover what processes exist and what parameters each one accepts
        before building the sequence.

        **Example response:**
        ```json
        {
          "React": {
            "label": "React",
            "description": "Main reaction step",
            "config_schema": {
              "properties": {
                "flow_rate": { "type": "string", "default": "5 ml/min" },
                "residence_time": { "type": "number", "default": 60 }
              }
            }
          },
          "clean": { "label": "clean", "description": "", "config_schema": {} }
        }
        ```
        """
        result: dict[str, Any] = {}
        for name, cls in self._processes.items():
            config_cls = _get_config_class(cls)
            result[name] = {
                "label": getattr(cls, "__process_label__", name),
                "description": getattr(cls, "__process_description__", ""),
                "config_schema": config_cls.model_json_schema(),
            }
        logger.info("GET /processes → {} process(es): {}", len(result), list(result))
        return result

    # ── Sequence ───────────────────────────────────────────────────────────────

    def get_sequence(self) -> list[dict[str, Any]]:
        """Return the current ordered process sequence.

        Each entry includes its index (used as the path parameter for PATCH/DELETE),
        a stable `slot_id` that survives index shifts, the process name, and its config.

        **Example response:**
        ```json
        [
          { "index": 0, "slot_id": "a1b2c3d4", "process_name": "React",
            "config": { "flow_rate": "5 ml/min" } },
          { "index": 1, "slot_id": "e5f6a7b8", "process_name": "clean",
            "config": {} }
        ]
        ```
        """
        result = [_entry_dict(i, e) for i, e in enumerate(self._entries)]
        logger.info("GET /sequence → {} entry(ies)", len(result))
        return result

    def add_to_sequence(self, body: AddToSequenceBody) -> dict[str, Any]:
        """Append a process to the end of the sequence.

        `config_overrides` is optional — omit it to use the process default config.
        The same process can be added multiple times; each entry gets an independent config.

        **Example request (default config):**
        ```json
        { "process_name": "React" }
        ```

        **Example request (with overrides):**
        ```json
        { "process_name": "React", "config_overrides": { "flow_rate": "10 ml/min" } }
        ```

        **Example response:**
        ```json
        { "index": 2, "slot_id": "c9d0e1f2", "process_name": "React",
          "config": { "flow_rate": "10 ml/min" } }
        ```
        """
        logger.info(
            "POST /sequence process_name={} overrides={}",
            body.process_name,
            body.config_overrides,
        )
        if self.is_running:
            logger.warning("POST /sequence rejected — workflow is running")
            raise HTTPException(
                status_code=409,
                detail="Cannot add to sequence while workflow is running",
            )
        cls = self._processes.get(body.process_name)
        if cls is None:
            logger.warning("POST /sequence unknown process: {!r}", body.process_name)
            raise HTTPException(
                status_code=404, detail=f"Unknown process: {body.process_name!r}"
            )
        config_cls = _get_config_class(cls)
        try:
            config = config_cls(**body.config_overrides)
        except ValidationError as e:
            logger.warning(
                "POST /sequence validation error for {!r}: {}",
                body.process_name,
                e.errors(),
            )
            raise HTTPException(status_code=422, detail=e.errors())
        entry = SequenceEntry(
            slot_id=uuid.uuid4().hex[:8],
            process_name=body.process_name,
            config=config,
        )
        self._entries.append(entry)
        result = _entry_dict(len(self._entries) - 1, entry)
        logger.info(
            "POST /sequence → slot_id={} index={}", entry.slot_id, result["index"]
        )
        return result

    def replace_sequence(
        self, items: list[ReplaceSequenceItem]
    ) -> list[dict[str, Any]]:
        """Replace the entire sequence atomically.

        All items are validated before any change is made — if one entry is invalid,
        the existing sequence is left untouched.

        **Example request:**
        ```json
        [
          { "process_name": "clean" },
          { "process_name": "React", "config_overrides": { "flow_rate": "5 ml/min" } },
          { "process_name": "React", "config_overrides": { "flow_rate": "10 ml/min" } }
        ]
        ```
        """
        logger.info(
            "PUT /sequence {} item(s): {}", len(items), [i.process_name for i in items]
        )
        if self.is_running:
            logger.warning("PUT /sequence rejected — workflow is running")
            raise HTTPException(
                status_code=409,
                detail="Cannot replace sequence while workflow is running",
            )
        new_entries: list[SequenceEntry] = []
        for i, item in enumerate(items):
            cls = self._processes.get(item.process_name)
            if cls is None:
                logger.warning(
                    "PUT /sequence item {}: unknown process {!r}", i, item.process_name
                )
                raise HTTPException(
                    status_code=404,
                    detail=f"Item {i}: unknown process {item.process_name!r}",
                )
            config_cls = _get_config_class(cls)
            try:
                config = config_cls(**item.config_overrides)
            except ValidationError as e:
                logger.warning(
                    "PUT /sequence item {} validation error for {!r}: {}",
                    i,
                    item.process_name,
                    e.errors(),
                )
                raise HTTPException(status_code=422, detail=f"Item {i}: {e.errors()}")
            new_entries.append(
                SequenceEntry(
                    slot_id=uuid.uuid4().hex[:8],
                    process_name=item.process_name,
                    config=config,
                )
            )
        self._entries.clear()
        self._entries.extend(new_entries)
        result = [_entry_dict(i, e) for i, e in enumerate(self._entries)]
        logger.info("PUT /sequence → sequence replaced with {} entry(ies)", len(result))
        return result

    def delete_sequence(self, index: int) -> None:
        """Remove the process at the given 0-based index from the sequence.

        All entries after the removed one shift down by one — use `GET /sequence`
        to refresh indices after a delete.

        **Example:** `DELETE /sequence/1` removes the second entry.

        Returns `204 No Content` on success.
        """
        logger.info("DELETE /sequence/{}", index)
        if self.is_running:
            logger.warning("DELETE /sequence/{} rejected — workflow is running", index)
            raise HTTPException(
                status_code=409,
                detail="Cannot delete from sequence while workflow is running",
            )
        if index < 0 or index >= len(self._entries):
            logger.warning(
                "DELETE /sequence/{} not found (sequence length={})",
                index,
                len(self._entries),
            )
            raise HTTPException(
                status_code=404, detail=f"No sequence entry at index {index}"
            )
        removed = self._entries.pop(index)
        logger.info(
            "DELETE /sequence/{} removed process={!r} slot_id={}",
            index,
            removed.process_name,
            removed.slot_id,
        )

    def patch_config(self, index: int, updates: dict[str, Any]) -> dict[str, Any]:
        """Update the config of the process at the given index.

        Send only the fields you want to change. The process name and `slot_id` are unchanged.
        Use `GET /sequence` to find the correct index first.

        **Example:** `PATCH /sequence/0/config`
        ```json
        { "flow_rate": "15 ml/min", "residence_time": 120 }
        ```

        **Example response:**
        ```json
        { "index": 0, "slot_id": "a1b2c3d4", "process_name": "React",
          "config": { "flow_rate": "15 ml/min", "residence_time": 120 } }
        ```
        """
        logger.info("PATCH /sequence/{}/config updates={}", index, updates)
        if self.is_running:
            logger.warning(
                "PATCH /sequence/{}/config rejected — workflow is running", index
            )
            raise HTTPException(
                status_code=409,
                detail="Cannot update config in sequence while workflow is running",
            )
        if index < 0 or index >= len(self._entries):
            logger.warning(
                "PATCH /sequence/{}/config not found (sequence length={})",
                index,
                len(self._entries),
            )
            raise HTTPException(
                status_code=404, detail=f"No sequence entry at index {index}"
            )
        entry = self._entries[index]
        try:
            entry.config = entry.config.model_copy(update=updates)
        except ValidationError as e:
            logger.warning(
                "PATCH /sequence/{}/config validation error: {}", index, e.errors()
            )
            raise HTTPException(status_code=422, detail=e.errors())
        result = _entry_dict(index, entry)
        logger.info("PATCH /sequence/{}/config → {}", index, result["config"])
        return result

    # ── Report ─────────────────────────────────────────────────────────────────

    def report(self) -> dict[str, Any]:
        return {
            "main_params": self.get_main_params(),
            "sequence_length": len(self._entries),
            "sequence": self.get_sequence(),
        }

    # ── Run ────────────────────────────────────────────────────────────────────

    async def execute(self) -> dict[str, str]:
        """Execute the configured sequence of processes.

        Runs each process in order using the current main parameters, sequence, and
        platform connectivity. Each `run_workflow` call is offloaded to a thread so
        the API remains responsive during execution — `GET /status` and `POST /stop`
        continue to work while this is running.

        Returns `409` if already running, `400` if the sequence is empty.
        On a node failure, returns `500` with the per-node error details.

        **Example response (success):**
        ```json
        { "status": "completed" }
        ```

        **Example response (stopped early):**
        ```json
        { "status": "completed" }
        ```
        *(The sequence loop exits cleanly when `POST /stop` is called between processes.)*
        """
        logger.info("POST /execute sequence_length={}", len(self._entries))
        if self.is_running:
            logger.warning("POST /execute rejected — already running")
            raise HTTPException(
                status_code=409, detail="Cannot execute while workflow is running"
            )
        if not self._entries:
            logger.warning("POST /execute rejected — sequence is empty")
            raise HTTPException(status_code=400, detail="No processes in sequence")

        # Build process instances from the already-configured sequence entries
        processes: list[Process] = []
        for entry in self._entries:
            process_class = self._processes.get(entry.process_name)
            if process_class is None:
                raise HTTPException(
                    status_code=404, detail=f"Unknown process: {entry.process_name!r}"
                )
            process_instance = process_class(config=entry.config)
            process_instance.main_parameter = self._params
            process_instance.platform = self._platform
            processes.append(process_instance)

        self.is_running = True
        try:
            for i, process in enumerate(processes):
                if not self.is_running:
                    logger.info(
                        "POST /execute stopped before process {}/{}",
                        i + 1,
                        len(processes),
                    )
                    break
                logger.info(
                    "POST /execute running process {}/{}: {!r}",
                    i + 1,
                    len(processes),
                    self._entries[i].process_name,
                )
                result = await asyncio.to_thread(
                    process.run_workflow, start_node="start"
                )
                if result.errors:
                    logger.error(
                        "POST /execute process {!r} failed: {}",
                        self._entries[i].process_name,
                        result.errors,
                    )
                    raise HTTPException(
                        status_code=500,
                        detail={str(k): str(v) for k, v in result.errors.items()},
                    )
                logger.info(
                    "POST /execute process {}/{} completed", i + 1, len(processes)
                )
        finally:
            self.is_running = False

        logger.info("POST /execute → completed")
        return {"status": "completed"}

    def status(self) -> dict[str, bool]:
        """Check whether a sequence execution is currently in progress.

        **Example response (idle):**
        ```json
        { "is_running": false }
        ```

        **Example response (running):**
        ```json
        { "is_running": true }
        ```
        """
        return {"is_running": self.is_running}

    def stop(self) -> dict[str, str]:
        """Request a graceful stop of the running sequence.

        Sets a flag that is checked between processes. The current process runs to
        completion before the sequence halts — mid-process interruption is not supported.
        Returns `400` if nothing is running.

        **Example response:**
        ```json
        { "status": "stop requested" }
        ```
        """
        logger.info("POST /stop")
        if not self.is_running:
            logger.warning("POST /stop rejected — workflow is not running")
            raise HTTPException(status_code=400, detail="Workflow is not running")
        self.is_running = False
        logger.info("POST /stop → stop requested")
        return {"status": "stop requested"}
