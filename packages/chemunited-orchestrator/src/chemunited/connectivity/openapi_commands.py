from __future__ import annotations

import re
from typing import Any, Literal, cast
from urllib.parse import urlsplit

import chemunited_core.protocols as protocol_module
from chemunited_core.protocols import CommandSignature, ComponentProtocol
from loguru import logger
from pydantic import Field, create_model
from pydantic.config import JsonDict

HttpMethod = Literal["GET", "PUT"]

_PARAMETER_LOCATIONS = {"path", "query"}
_VALID_FIELD_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def default_protocol_for_figure(
    figure: str,
    component_name: str,
) -> ComponentProtocol:
    protocol_cls = getattr(protocol_module, f"{figure}Protocols", None)
    if (
        isinstance(protocol_cls, type)
        and issubclass(protocol_cls, ComponentProtocol)
        and protocol_cls is not ComponentProtocol
    ):
        return protocol_cls(component_name)
    return ComponentProtocol(component_name)


def reset_protocol_to_default(component: Any) -> ComponentProtocol:
    protocol = default_protocol_for_figure(component.inf.figure, component.name)
    component.protocols = protocol
    return protocol


def apply_openapi_commands(component: Any, openapi: dict[str, Any]) -> int:
    protocol = reset_protocol_to_default(component)
    before = set(protocol.commands)
    merge_openapi_commands(
        protocol=protocol,
        openapi=openapi,
        device=_url_segment(str(component.url), 0),
        component=_url_segment(str(component.url), 1),
    )
    return len(set(protocol.commands) - before)


def merge_openapi_commands(
    *,
    protocol: ComponentProtocol,
    openapi: dict[str, Any],
    device: str,
    component: str,
) -> int:
    paths = openapi.get("paths")
    if not isinstance(paths, dict):
        return 0

    covered = _covered_commands(protocol)
    added = 0
    for raw_path, path_item in paths.items():
        parsed = _parse_component_path(raw_path, device, component)
        if parsed is None or not isinstance(path_item, dict):
            continue

        command = parsed
        shared_parameters = _parameter_names(path_item.get("parameters"))
        for raw_method, operation in path_item.items():
            method = raw_method.upper()
            if method not in {"GET", "PUT"} or not isinstance(operation, dict):
                continue
            typed_method = cast(HttpMethod, method)
            if (typed_method, command) in covered:
                continue

            parameter_names = sorted(
                shared_parameters
                | _parameter_names(operation.get("parameters"))
                | _request_body_parameter_names(operation.get("requestBody"))
            )
            key = _unique_command_key(protocol.commands, command, typed_method)
            protocol.commands[key] = _build_command_signature_class(
                protocol_name=type(protocol).__name__,
                command=command,
                method=typed_method,
                parameter_names=parameter_names,
            )
            covered.add((typed_method, command))
            added += 1
    return added


def _covered_commands(protocol: ComponentProtocol) -> set[tuple[str, str]]:
    covered: set[tuple[str, str]] = set()
    for command_class in protocol.commands.values():
        if not (
            isinstance(command_class, type)
            and issubclass(command_class, CommandSignature)
        ):
            continue
        command_field = command_class.model_fields.get("command")
        method_field = command_class.model_fields.get("method")
        if command_field is None or method_field is None:
            continue
        command = command_field.default
        method = method_field.default
        if isinstance(command, str) and method in {"GET", "PUT"}:
            covered.add((method, command))
    return covered


def _parse_component_path(
    raw_path: str,
    device: str,
    component: str,
) -> str | None:
    segments = [segment for segment in raw_path.strip("/").split("/") if segment]
    if len(segments) < 3:
        return None
    if segments[0] != device or segments[1] != component:
        return None
    return "/".join(segments[2:])


def _parameter_names(parameters: Any) -> set[str]:
    if not isinstance(parameters, list):
        return set()

    names: set[str] = set()
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        if parameter.get("in") not in _PARAMETER_LOCATIONS:
            continue
        name = parameter.get("name")
        if isinstance(name, str) and _is_valid_field_name(name):
            names.add(name)
    return names


def _request_body_parameter_names(request_body: Any) -> set[str]:
    if not isinstance(request_body, dict):
        return set()

    names: set[str] = set()
    content = request_body.get("content")
    if not isinstance(content, dict):
        return names

    for media_type in content.values():
        if not isinstance(media_type, dict):
            continue
        names |= _schema_property_names(media_type.get("schema"))
    return names


def _schema_property_names(schema: Any) -> set[str]:
    if not isinstance(schema, dict):
        return set()

    if "$ref" in schema:
        return set()

    properties = schema.get("properties")
    if isinstance(properties, dict):
        return {
            name
            for name in properties
            if isinstance(name, str) and _is_valid_field_name(name)
        }

    items = schema.get("items")
    if isinstance(items, dict):
        return _schema_property_names(items)

    return set()


def _build_command_signature_class(
    *,
    protocol_name: str,
    command: str,
    method: HttpMethod,
    parameter_names: list[str],
) -> type[CommandSignature]:
    fields: dict[str, Any] = {
        "command": (str, Field(default=command)),
        "method": (Literal["GET", "PUT"], Field(default=method)),
    }
    for name in parameter_names:
        fields[name] = (
            str,
            Field(
                default="",
                title=_title(name),
                json_schema_extra=cast(JsonDict, {"group": "FlowChem Parameters"}),
            ),
        )

    class_name = _dynamic_class_name(protocol_name, command, method)
    return create_model(class_name, __base__=CommandSignature, **fields)


def _dynamic_class_name(protocol_name: str, command: str, method: str) -> str:
    parts = re.split(r"[^A-Za-z0-9]+", f"{protocol_name}_{method}_{command}")
    stem = "".join(part[:1].upper() + part[1:] for part in parts if part)
    return f"{stem or 'FlowChem'}Parameter"


def _unique_command_key(
    commands: dict[str, type[CommandSignature]],
    command: str,
    method: str,
) -> str:
    if command not in commands:
        return command

    base = f"{method.lower()}:{command}"
    if base not in commands:
        return base

    index = 2
    while f"{base}:{index}" in commands:
        index += 1
    return f"{base}:{index}"


def _is_valid_field_name(name: str) -> bool:
    return (
        bool(_VALID_FIELD_RE.match(name)) and name not in CommandSignature.model_fields
    )


def _title(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").title()


def _url_segment(url: str, index: int) -> str:
    segments = [segment for segment in urlsplit(url).path.split("/") if segment]
    if index >= len(segments):
        logger.debug(
            f"Could not inspect FlowChem command URL without segment {index}: {url}"
        )
        return ""
    return segments[index]
