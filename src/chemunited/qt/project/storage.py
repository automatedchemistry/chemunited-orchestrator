from __future__ import annotations

import importlib.util
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from chemunited.qt.project.writer import render_python_script
from chemunited.qt.utils.files import load_attribute

_PACK_EXCLUDE = {".git", ".gitignore", ".chemunited_session"}
_PROTOCOLS_SKIP = {"__init__", "main_parameters"}


# ── Pack / Unpack (unchanged) ──────────────────────────────────────────────────


def pack(working_dir: Path, destination: Path) -> None:
    destination = destination.with_suffix(".chemunited")
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in working_dir.rglob("*"):
            if file.is_file() and not _is_excluded(file, working_dir):
                zf.write(file, file.relative_to(working_dir))


def unpack(chemunited_file: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(chemunited_file, "r") as zf:
        zf.extractall(target_dir)


def _is_excluded(file: Path, root: Path) -> bool:
    return any(part in _PACK_EXCLUDE for part in file.relative_to(root).parts)


# ── Draw (unchanged) ───────────────────────────────────────────────────────────


def save_draw(working_dir: Path, draw_data: dict) -> None:
    path = working_dir / "draw" / "setup.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_draw_script(working_dir, draw_data), encoding="utf-8")


def load_draw(working_dir: Path) -> dict:
    path = working_dir / "draw" / "setup.py"
    if not path.exists():
        return {"components": [], "connections": [], "canvas": {}}
    build_draw = load_attribute(
        path,
        "build_draw",
        f"_chemunited_draw_setup_{abs(hash(path.resolve()))}",
    )
    if not callable(build_draw):
        raise ValueError(f"Draw setup file must define build_draw(platform): {path}")

    recorder = _DrawRecorder()
    build_draw(recorder)
    return recorder.data()


class _DrawRecorder:
    def __init__(self) -> None:
        self.components: list[dict] = []
        self.connections: list[dict] = []

    def add_component(self, **payload) -> None:
        self.components.append(dict(payload))

    def add_connection(
        self,
        origin: str,
        destiny: str | None = None,
        origin_port: int = 2,
        destiny_port: int | None = None,
        destination: str | None = None,
        destination_port: int | None = None,
        **payload,
    ) -> None:
        target = destiny if destiny is not None else destination
        if target is None:
            raise ValueError("Draw setup connection is missing a destiny.")

        target_port = (
            destiny_port
            if destiny_port is not None
            else destination_port if destination_port is not None else 1
        )
        connection = {
            "origin": origin,
            "destination": target,
            "origin_port": origin_port,
            "destination_port": target_port,
        }
        connection.update(payload)
        self.connections.append(connection)

    def data(self) -> dict:
        return {"components": self.components, "connections": self.connections}


def _render_draw_script(working_dir: Path, draw_data: dict) -> str:
    generated_at = datetime.now(timezone.utc).isoformat()
    draw_body = _render_draw_body(draw_data)
    template = render_python_script(
        script="project",
        overwrite={
            "---PROJECT_NAME---": working_dir.name,
            "---DATE---": generated_at,
            "---DATA---": generated_at,
        },
    )
    return template.replace("    ---DRAW---", draw_body).replace(
        "---DRAW---", draw_body.lstrip()
    )


def _render_draw_body(draw_data: dict) -> str:
    calls = []
    for component in draw_data.get("components", []):
        calls.append(_render_call("platform.add_component", component, "component"))

    for connection in draw_data.get("connections", []):
        calls.append(_render_call("platform.add_connection", connection, "connection"))

    if not calls:
        return "    pass\n"
    return "\n\n".join(calls) + "\n"


def _render_call(function_name: str, payload: dict, payload_type: str) -> str:
    lines = [f"    {function_name}("]
    for key, value in _ordered_payload(payload, payload_type).items():
        lines.append(f"        {key}={_format_python_value(key, value)},")
    lines.append("    )")
    return "\n".join(lines)


def _ordered_payload(payload: dict, payload_type: str) -> dict:
    normalized = dict(payload)
    if payload_type == "connection":
        if "destination" in normalized and "destiny" not in normalized:
            normalized["destiny"] = normalized.pop("destination")
        if "destination_port" in normalized and "destiny_port" not in normalized:
            normalized["destiny_port"] = normalized.pop("destination_port")

    preferred = {
        "component": ("name", "figure", "position", "angle"),
        "connection": ("origin", "destiny", "origin_port", "destiny_port"),
    }[payload_type]
    ordered = {key: normalized.pop(key) for key in preferred if key in normalized}
    ordered.update({key: normalized[key] for key in sorted(normalized)})
    return ordered


def _format_python_value(key: str, value) -> str:
    if key == "position" and isinstance(value, list):
        return repr(tuple(value))
    return repr(value)


# ── Process files (replaces workflow + modules + process_parameters) ───────────


def save_process(working_dir: Path, process_name: str, content: str) -> None:
    path = working_dir / "protocols" / f"{process_name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _refresh_protocols_init(working_dir)


def load_process(working_dir: Path, process_name: str) -> str:
    path = working_dir / "protocols" / f"{process_name}.py"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def delete_process(working_dir: Path, process_name: str) -> None:
    path = working_dir / "protocols" / f"{process_name}.py"
    if path.exists():
        path.unlink()
    _refresh_protocols_init(working_dir)


def rename_process(working_dir: Path, old_name: str, new_name: str) -> None:
    old_path = working_dir / "protocols" / f"{old_name}.py"
    new_path = working_dir / "protocols" / f"{new_name}.py"
    if old_path.exists():
        old_path.rename(new_path)
    _refresh_protocols_init(working_dir)


def duplicate_process(working_dir: Path, source_name: str, new_name: str) -> None:
    content = load_process(working_dir, source_name)
    # Update the class name inside the file to match the new name
    old_class = _class_name(source_name)
    new_class = _class_name(new_name)
    content = content.replace(old_class, new_class)
    content = content.replace(
        f'__process_label__ = "{source_name}"',
        f'__process_label__ = "{new_name}"',
    )
    save_process(working_dir, new_name, content)


def list_processes(working_dir: Path) -> list[str]:
    protocols_dir = working_dir / "protocols"
    if not protocols_dir.exists():
        return []
    return [
        p.stem
        for p in sorted(protocols_dir.glob("*.py"))
        if p.stem not in _PROTOCOLS_SKIP
    ]


def load_process_classes(working_dir: Path) -> dict:
    """
    Dynamically import protocols/__init__.py and return the PROCESSES dict.
    Returns {} if the package cannot be loaded.
    """
    init_path = working_dir / "protocols" / "__init__.py"
    if not init_path.exists():
        return {}
    try:
        spec = importlib.util.spec_from_file_location(
            "protocols",
            init_path,
            submodule_search_locations=[str(working_dir / "protocols")],
        )
        if spec is None or spec.loader is None:
            return {}
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, "PROCESSES", {})
    except Exception:
        return {}


# ── Main parameters ────────────────────────────────────────────────────────────


def save_main_parameters(working_dir: Path, content: str) -> None:
    path = working_dir / "protocols" / "main_parameters.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_main_parameters(working_dir: Path) -> str:
    path = working_dir / "protocols" / "main_parameters.py"
    return path.read_text(encoding="utf-8") if path.exists() else ""


# ── Connectivity (unchanged) ───────────────────────────────────────────────────


def save_connectivity(working_dir: Path, data: dict) -> None:
    path = working_dir / "connectivity" / "associations.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_connectivity(working_dir: Path) -> dict:
    path = working_dir / "connectivity" / "associations.json"
    if not path.exists():
        return {"server_url": "", "associations": []}
    return json.loads(path.read_text(encoding="utf-8"))


# ── protocols/__init__.py registry ────────────────────────────────────────────


def _refresh_protocols_init(working_dir: Path) -> None:
    protocols_dir = working_dir / "protocols"
    names = list_processes(working_dir)
    lines = ['"""Auto-generated by ChemUnited — do not edit manually."""\n\n']
    for name in names:
        cls = _class_name(name)
        lines.append(f"from .{name} import {cls}\n")
    lines.append("\nPROCESSES = {\n")
    for name in names:
        cls = _class_name(name)
        lines.append(f'    "{name}": {cls},\n')
    lines.append("}\n")
    (protocols_dir / "__init__.py").write_text("".join(lines), encoding="utf-8")


def _class_name(process_name: str) -> str:
    """react -> ReactProcess,  my_process -> MyProcessProcess"""
    return process_name.replace("_", " ").title().replace(" ", "") + "Process"
