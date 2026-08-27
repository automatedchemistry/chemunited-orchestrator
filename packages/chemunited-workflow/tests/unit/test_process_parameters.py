"""Unit tests for Process.load_parameters (Step 02)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from tests.helpers import (
    make_project_tree,
    write_source,
)


def _load_process(
    process_dir: Path, config_values: dict | None = None, process_index: int = 0
):
    """Dynamically import MyProcess from process_dir and instantiate it."""
    path = process_dir / "my_process.py"
    spec = importlib.util.spec_from_file_location("my_process", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Required so inspect.getfile can resolve the class back to its source file
    sys.modules["my_process"] = module
    spec.loader.exec_module(module)
    config = module.MyConfig(**(config_values or {}))
    return module.MyProcess(config=config, process_index=process_index)


# ── Phase 1: MainParameter class ─────────────────────────────────────────────


def test_no_main_parameters_file(tmp_path):
    dirs = make_project_tree(tmp_path)
    # Remove main_parameters.py
    (dirs["process_dir"] / "main_parameters.py").unlink()
    process = _load_process(dirs["process_dir"])
    result = process.load_parameters()
    assert result is True
    assert process.main_parameters is None


def test_main_parameters_class_not_found(tmp_path):
    dirs = make_project_tree(tmp_path)
    write_source(dirs["process_dir"], "main_parameters.py", "# no class here\n")
    process = _load_process(dirs["process_dir"])
    result = process.load_parameters()
    assert result is False


def test_main_parameters_not_basemodel(tmp_path):
    dirs = make_project_tree(tmp_path)
    write_source(
        dirs["process_dir"],
        "main_parameters.py",
        "class MainParameter:\n    pass\n",
    )
    process = _load_process(dirs["process_dir"])
    result = process.load_parameters()
    assert result is False


def test_valid_main_parameters_loaded(tmp_path):
    dirs = make_project_tree(tmp_path)
    process = _load_process(dirs["process_dir"])
    result = process.load_parameters()
    assert result is True
    assert process.main_parameters is not None
    assert process.main_parameters.reagent_volume_ml == 5.0  # type: ignore[union-attr]


def test_main_parameters_required_field_fails(tmp_path):
    dirs = make_project_tree(tmp_path)
    write_source(
        dirs["process_dir"],
        "main_parameters.py",
        "from pydantic import BaseModel\nclass MainParameter(BaseModel):\n    required: float\n",
    )
    process = _load_process(dirs["process_dir"])
    result = process.load_parameters()
    assert result is False


# ── Phase 2: historic JSON ────────────────────────────────────────────────────


def test_no_historic_file_returns_true(tmp_path):
    dirs = make_project_tree(tmp_path)
    process = _load_process(dirs["process_dir"])
    result = process.load_parameters()
    assert result is True


def test_historic_json_main_parameter_without_class_fails(tmp_path):
    dirs = make_project_tree(tmp_path)
    (dirs["process_dir"] / "main_parameters.py").unlink()
    data = {
        "main_parameter": {"reagent_volume_ml": 9.0},
        "my_process_0": {"value": 2.5},
    }
    (dirs["historic_dir"] / "parameters.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    process = _load_process(dirs["process_dir"])
    result = process.load_parameters()
    assert result is False


def test_historic_json_overrides_main_parameters(tmp_path):
    dirs = make_project_tree(tmp_path)
    data = {
        "main_parameter": {"reagent_volume_ml": 9.0, "target_temperature_c": 60.0},
        "my_process_0": {"value": 2.5},
    }
    (dirs["historic_dir"] / "parameters.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    process = _load_process(dirs["process_dir"])
    result = process.load_parameters()
    assert result is True
    assert process.main_parameters.reagent_volume_ml == 9.0  # type: ignore[union-attr]
    assert process.main_parameters.target_temperature_c == 60.0  # type: ignore[union-attr]


def test_historic_json_missing_process_key_fails(tmp_path):
    dirs = make_project_tree(tmp_path)
    data = {"main_parameter": {"reagent_volume_ml": 5.0, "target_temperature_c": 25.0}}
    (dirs["historic_dir"] / "parameters.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    process = _load_process(dirs["process_dir"])
    result = process.load_parameters()
    assert result is False


def test_historic_json_overrides_config(tmp_path):
    dirs = make_project_tree(tmp_path)
    data = {
        "main_parameter": {"reagent_volume_ml": 5.0, "target_temperature_c": 25.0},
        "my_process_0": {"value": 2.5},
    }
    (dirs["historic_dir"] / "parameters.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    process = _load_process(dirs["process_dir"])
    result = process.load_parameters()
    assert result is True
    assert process.config.value == 2.5  # type: ignore[union-attr]


def test_process_index_1_looks_up_correct_key(tmp_path):
    dirs = make_project_tree(tmp_path)
    data = {
        "main_parameter": {"reagent_volume_ml": 5.0, "target_temperature_c": 25.0},
        "my_process_1": {"value": 0.8},
    }
    (dirs["historic_dir"] / "parameters.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    process = _load_process(dirs["process_dir"], process_index=1)
    result = process.load_parameters()
    assert result is True
    assert process.config.value == 0.8  # type: ignore[union-attr]


def test_historic_json_invalid_config_values_fails(tmp_path):
    dirs = make_project_tree(tmp_path)
    data = {
        "main_parameter": {"reagent_volume_ml": 5.0, "target_temperature_c": 25.0},
        "my_process_0": {"value": "not-a-number"},
    }
    (dirs["historic_dir"] / "parameters.json").write_text(
        json.dumps(data), encoding="utf-8"
    )
    process = _load_process(dirs["process_dir"])
    result = process.load_parameters()
    assert result is False


def test_historic_json_invalid_json_fails(tmp_path):
    dirs = make_project_tree(tmp_path)
    (dirs["historic_dir"] / "parameters.json").write_text("NOT JSON", encoding="utf-8")
    process = _load_process(dirs["process_dir"])
    result = process.load_parameters()
    assert result is False
