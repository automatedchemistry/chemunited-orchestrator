from __future__ import annotations

import ast
import importlib.util
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from chemunited.qt.protocols.workflows import ProcessWorkflow
from chemunited.qt.project.writer import render_python_script, write_python_script
from chemunited.qt.utils.files import load_attribute

_PACK_EXCLUDE = {".git", ".gitignore", ".chemunited_session", "__pycache__"}
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


# ── API script ────────────────────────────────────────────────────────────────


def write_api_script(working_dir: Path, port: int = 3116) -> None:
    write_python_script(
        working_dir / "api.py",
        script="api",
        overwrite={
            "---PROJECT_NAME---": working_dir.name,
            "---PORT---": str(port),
        },
    )


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
    try:
        build_draw(recorder)
    except Exception as exc:
        raise ValueError(
            f"Error in draw setup script '{path.name}': {type(exc).__name__}: {exc}"
        ) from exc
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


def sync_process(
    working_dir: Path,
    process_name: str,
    workflow: ProcessWorkflow,
) -> bool:
    path = working_dir / "protocols" / f"{process_name}.py"
    if not path.exists():
        save_process(
            working_dir,
            process_name,
            _render_process_script(working_dir, process_name, workflow),
        )
        return True

    original = path.read_text(encoding="utf-8")
    updated = _sync_process_content(original, process_name, workflow)
    if updated is None:
        return False
    if updated != original:
        path.write_text(updated, encoding="utf-8")
    _refresh_protocols_init(working_dir)
    return True


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
        if new_path.exists():
            raise FileExistsError(f"Process file already exists: {new_path}")
        content = _retitle_process_content(
            old_path.read_text(encoding="utf-8"),
            old_name,
            new_name,
        )
        new_path.write_text(content, encoding="utf-8")
        old_path.unlink()
    _refresh_protocols_init(working_dir)


def duplicate_process(working_dir: Path, source_name: str, new_name: str) -> None:
    content = load_process(working_dir, source_name)
    content = _retitle_process_content(content, source_name, new_name)
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
    import sys

    init_path = working_dir / "protocols" / "__init__.py"
    if not init_path.exists():
        return {}

    pkg_name = f"_chemunited_protocols_{abs(hash(working_dir.resolve()))}"
    try:
        spec = importlib.util.spec_from_file_location(
            pkg_name,
            init_path,
            submodule_search_locations=[str(working_dir / "protocols")],
        )
        if spec is None or spec.loader is None:
            return {}
        module = importlib.util.module_from_spec(spec)
        sys.modules[pkg_name] = module
        spec.loader.exec_module(module)
        return getattr(module, "PROCESSES", {})
    except Exception:
        return {}
    finally:
        sys.modules.pop(pkg_name, None)


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
    """react -> ReactProcess,  my_process -> MyProcessProcess,  ReactRenamed -> ReactRenamedProcess"""
    parts = process_name.split("_")
    return "".join(p[:1].upper() + p[1:] for p in parts if p) + "Process"


def _render_process_script(
    working_dir: Path,
    process_name: str,
    workflow: ProcessWorkflow,
) -> str:
    class_name = _class_name(process_name)
    template = render_python_script(
        script="process",
        overwrite={
            "---DATE---": datetime.now(timezone.utc).isoformat(),
            "---PROJECT_NAME---": working_dir.name,
            "---PROCESS_NAME---": process_name,
            "---CLASS_NAME---": class_name,
            "---PROCESS_LABEL---": process_name,
            "---PROCESS_DESCRIPTION---": "",
        },
    )
    workflow_definition = _render_workflow_definition(workflow)
    content = template.replace("        ---WORKFLOW_DEFINITION---", workflow_definition)
    method_block = _render_new_process_methods(workflow)
    if not method_block:
        return content
    return content.replace(
        "\n\n# =============================================",
        f"\n\n{method_block}\n\n# =============================================",
        1,
    )


def _render_build_workflow_method(workflow: ProcessWorkflow) -> str:
    workflow_definition = _render_workflow_definition(workflow)
    return (
        "    def build_workflow(self) -> nx.DiGraph:\n"
        "        graph = nx.DiGraph()\n\n"
        f"{workflow_definition}\n\n"
        "        return graph"
    )


def _render_workflow_definition(workflow: ProcessWorkflow) -> str:
    indent = "        "
    sections = [block.to_script(indent) for _, block in workflow.iter_blocks()] + [
        conn.to_script(start, end, indent)
        for start, end, conn in workflow.iter_connections()
    ]
    return "\n\n".join(sections) if sections else f"{indent}pass"


def _sync_process_content(
    original: str,
    process_name: str,
    workflow: ProcessWorkflow,
) -> str | None:
    try:
        tree = ast.parse(original)
    except SyntaxError:
        return None

    class_name = _class_name(process_name)
    class_node = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        ),
        None,
    )
    if class_node is None or not class_node.body:
        return None

    build_workflow_node = next(
        (
            node
            for node in class_node.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "build_workflow"
        ),
        None,
    )
    if build_workflow_node is None:
        return None

    previous_managed_methods = _extract_managed_methods(build_workflow_node)
    if previous_managed_methods is None:
        return None

    new_managed_methods = _workflow_managed_methods(workflow)
    return _rewrite_process_class(
        original,
        class_node,
        build_workflow_node,
        previous_managed_methods,
        new_managed_methods,
        workflow,
    )


def _extract_managed_methods(
    build_workflow_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[str] | None:
    names: list[str] = []
    saw_add_node = False

    for node in ast.walk(build_workflow_node):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_node"
        ):
            continue
        saw_add_node = True
        method_name = _extract_method_name_from_add_node(node)
        if method_name is None:
            return None
        if method_name not in names:
            names.append(method_name)

    return names if saw_add_node else []


def _extract_method_name_from_add_node(node: ast.Call) -> str | None:
    method_name: str | None = None
    node_id: str | None = None

    if node.args:
        node_id = _string_constant(node.args[0])

    for keyword in node.keywords:
        if keyword.arg == "method":
            method_name = _string_constant(keyword.value) or method_name
            continue
        if keyword.arg == "node_id":
            node_id = _string_constant(keyword.value) or node_id
            continue
        if keyword.arg is None:
            extracted = _extract_method_name_from_nodespec(keyword.value)
            if extracted is None:
                continue
            extracted_method, extracted_node_id = extracted
            method_name = extracted_method or method_name
            node_id = extracted_node_id or node_id

    return method_name or node_id


def _extract_method_name_from_nodespec(
    node: ast.AST,
) -> tuple[str | None, str | None] | None:
    for child in ast.walk(node):
        if not (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "WorkflowNodeSpec"
        ):
            continue

        method_name: str | None = None
        node_id: str | None = None
        for keyword in child.keywords:
            if keyword.arg == "method":
                method_name = _string_constant(keyword.value)
            elif keyword.arg == "node_id":
                node_id = _string_constant(keyword.value)
        return method_name, node_id

    return None


def _string_constant(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _workflow_managed_methods(workflow: ProcessWorkflow) -> list[str]:
    names: list[str] = []
    for _, block in workflow.iter_blocks():
        if not block.method or block.method in names:
            continue
        names.append(block.method)
    return names


def _rewrite_process_class(
    original: str,
    class_node: ast.ClassDef,
    build_workflow_node: ast.FunctionDef | ast.AsyncFunctionDef,
    previous_managed_methods: list[str],
    new_managed_methods: list[str],
    workflow: ProcessWorkflow,
) -> str:
    lines = original.splitlines(keepends=True)
    body_items = list(class_node.body)
    function_items = [
        node
        for node in body_items
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    existing_method_names = {node.name for node in function_items}
    obsolete_methods = {
        name
        for name in previous_managed_methods
        if name not in new_managed_methods and name in existing_method_names
    }
    preserved_managed_names = {
        name
        for name in previous_managed_methods
        if name in new_managed_methods and name in existing_method_names
    }
    missing_methods = [
        name for name in new_managed_methods if name not in existing_method_names
    ]
    stub_block = "\n\n".join(_render_method_stub(name) for name in missing_methods)

    body_start = _node_start_offset(body_items[0], lines)
    class_end = _node_end_offset(class_node, lines)
    chunks = [original[:body_start]]
    current = body_start

    preserved_items = [
        node
        for node in function_items
        if node.name in preserved_managed_names and node.name != "build_workflow"
    ]
    insert_after_item = preserved_items[-1] if preserved_items else None
    build_index = body_items.index(build_workflow_node)
    insert_before_item = None
    if insert_after_item is None and stub_block:
        insert_before_item = next(
            (
                node
                for node in body_items[build_index + 1 :]
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name not in obsolete_methods
            ),
            None,
        )

    inserted_stubs = False
    for node in body_items:
        start = _node_start_offset(node, lines)
        end = _node_end_offset(node, lines)

        if node is build_workflow_node:
            line_start = _node_line_start_offset(node, lines)
            chunks.append(original[current:line_start])
            chunks.append(_render_build_workflow_method(workflow))
            current = end
            continue

        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name in obsolete_methods
        ):
            chunks.append(original[current:start])
            current = end
            continue

        if node is insert_before_item and not inserted_stubs and stub_block:
            line_start = _node_line_start_offset(node, lines)
            chunks.append(original[current:line_start])
            chunks.append(stub_block)
            chunks.append("\n\n")
            chunks.append(original[line_start:end])
            current = end
            inserted_stubs = True
            continue

        chunks.append(original[current:end])
        current = end

        if node is insert_after_item and not inserted_stubs and stub_block:
            chunks.append("\n\n")
            chunks.append(stub_block)
            inserted_stubs = True

    remainder = original[current:class_end]
    if not inserted_stubs and stub_block:
        chunks.append(remainder)
        _append_separated_block(chunks, stub_block)
        remainder = ""
    else:
        chunks.append(remainder)

    chunks.append(original[class_end:])
    return "".join(chunks)


def _append_separated_block(chunks: list[str], block: str) -> None:
    if chunks:
        previous = chunks[-1]
        if previous.endswith("\n\n"):
            pass
        elif previous.endswith("\n"):
            chunks.append("\n")
        else:
            chunks.append("\n\n")
        chunks.append(block)
        return
    chunks.append(block)


def _node_start_offset(node: ast.AST, lines: list[str]) -> int:
    decorators = getattr(node, "decorator_list", [])
    start_node = decorators[0] if decorators else node
    return _line_col_to_offset(lines, start_node.lineno, start_node.col_offset)


def _node_line_start_offset(node: ast.AST, lines: list[str]) -> int:
    decorators = getattr(node, "decorator_list", [])
    start_node = decorators[0] if decorators else node
    return _line_col_to_offset(lines, start_node.lineno, 0)


def _node_end_offset(node: ast.AST, lines: list[str]) -> int:
    return _line_col_to_offset(lines, node.end_lineno, node.end_col_offset)


def _line_col_to_offset(lines: list[str], lineno: int, col_offset: int) -> int:
    return sum(len(line) for line in lines[: lineno - 1]) + col_offset


def _render_method_stub(method_name: str) -> str:
    status_message = _default_status_message(method_name)
    return (
        f"    def {method_name}(self, ctx: NodeExecutionContext) -> bool:\n"
        f'        ctx.runtime.status_message = "{status_message}"\n'
        "        return True"
    )


def _default_status_message(method_name: str) -> str:
    if method_name == "start":
        return "Started."
    if method_name == "finish":
        return "Finished."
    label = method_name.replace("_", " ").title()
    return f"{label} ran."


def _render_new_process_methods(workflow: ProcessWorkflow) -> str:
    return "\n\n".join(
        _render_method_stub(method_name)
        for method_name in _workflow_managed_methods(workflow)
        if method_name not in {"start", "finish"}
    )


def _retitle_process_content(
    content: str, source_name: str, new_name: str
) -> str:
    old_class = _class_name(source_name)
    new_class = _class_name(new_name)
    updated = content.replace(old_class, new_class)
    updated = updated.replace(
        f"# Process name: {source_name}",
        f"# Process name: {new_name}",
    )
    updated = updated.replace(f'"""{source_name}"""', f'"""{new_name}"""')
    updated = updated.replace(
        f'__process_label__ = "{source_name}"',
        f'__process_label__ = "{new_name}"',
    )
    return updated
