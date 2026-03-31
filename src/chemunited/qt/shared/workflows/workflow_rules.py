from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, TypedDict

from chemunited.shared.enums.protocols_enum import ProtocolBlock
from chemunited.shared.workflows.exceptions import WorkflowRuleViolation


@dataclass(frozen=True, slots=True)
class TerminalBlockSpec:
    name: str
    block_tag: ProtocolBlock
    pos: tuple[float, float]
    protected: bool = True


class ConnectionAttributes(TypedDict, total=False):
    start_role: str
    condition: bool | None
    loopback: bool
    trigger_on: bool


def default_terminal_block_specs() -> tuple[TerminalBlockSpec, ...]:
    return (
        TerminalBlockSpec(
            name="start",
            block_tag=ProtocolBlock.START,
            pos=(200.0, 300.0),
        ),
        TerminalBlockSpec(
            name="end",
            block_tag=ProtocolBlock.END,
            pos=(800.0, 300.0),
        ),
    )


def generate_block_name(
    existing_names: Iterable[str], block_tag: ProtocolBlock
) -> str:
    prefix = {
        ProtocolBlock.SCRIPT: "script",
        ProtocolBlock.LOOP: "loop",
        ProtocolBlock.IF: "conditional",
    }.get(block_tag)
    if prefix is None:
        raise WorkflowRuleViolation(f"Cannot auto-generate a block name for {block_tag}")

    existing = set(existing_names)
    index = 1
    while f"{prefix}_{index}" in existing:
        index += 1
    return f"{prefix}_{index}"


def validate_connection_request(
    *,
    start_name: str,
    end_name: str,
    start_block_tag: ProtocolBlock,
    start_role: str,
    end_role: str,
    existing_connection: bool,
    has_outgoing_loopback: bool,
) -> None:
    if start_name == end_name:
        raise WorkflowRuleViolation("A block cannot connect to itself")
    if start_role == "left":
        raise WorkflowRuleViolation("Connections cannot start from an input port")
    if end_role != "left":
        raise WorkflowRuleViolation("Connections must end at an input port")
    if existing_connection:
        raise WorkflowRuleViolation("This connection already exists")
    if (
        start_block_tag == ProtocolBlock.LOOP
        and start_role in {"top", "bottom"}
        and has_outgoing_loopback
    ):
        raise WorkflowRuleViolation("Loop blocks may only have one outgoing loopback")


def derive_connection_attributes(
    start_block_tag: ProtocolBlock, start_role: str
) -> ConnectionAttributes:
    metadata: ConnectionAttributes = {"start_role": start_role}

    if start_block_tag == ProtocolBlock.LOOP and start_role in {"top", "bottom"}:
        metadata["loopback"] = True
        metadata["trigger_on"] = False
        metadata["condition"] = True
        return metadata

    if start_block_tag == ProtocolBlock.IF:
        metadata["condition"] = start_role != "top"
        return metadata

    metadata["condition"] = True
    return metadata


def incoming_port_count(loopback_flags: Iterable[bool]) -> int:
    return sum(1 for is_loopback in loopback_flags if not is_loopback)


def resolve_render_start_role(
    block_tag: ProtocolBlock,
    *,
    start_role: str | None,
    loopback: bool,
    trigger_on: bool,
    condition: bool | None,
) -> str:
    if start_role in {"top", "bottom", "right"}:
        return start_role
    if loopback:
        return "top" if trigger_on else "bottom"
    if block_tag == ProtocolBlock.IF:
        return "bottom" if condition is not False else "top"
    return "right"
