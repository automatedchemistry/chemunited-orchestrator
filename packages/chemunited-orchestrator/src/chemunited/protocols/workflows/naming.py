"""Naming helpers for generated workflow/process Python code."""

PROCESS_CLASS_NAME = "CustomProcess"
PROCESS_CONFIG_CLASS_NAME = "ProcessConfig"


def process_class_name(_process_name: str = "") -> str:
    return PROCESS_CLASS_NAME


def process_config_class_name(_process_name: str = "") -> str:
    return PROCESS_CONFIG_CLASS_NAME
