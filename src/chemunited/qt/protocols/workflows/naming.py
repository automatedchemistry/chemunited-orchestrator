"""Naming helpers for generated workflow/process Python code."""


def process_class_name(process_name: str) -> str:
    parts = process_name.split("_")
    return "".join(part[:1].upper() + part[1:] for part in parts if part) + "Process"
