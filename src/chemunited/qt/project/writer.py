from pathlib import Path

import black  # type: ignore[import-not-found]
from loguru import logger
from PyQt5.QtCore import QFile, QTextStream


def _resource_fallback_path(path: str) -> Path | None:
    prefix = ":/default_files/"
    if not path.startswith(prefix):
        return None
    return (
        Path(__file__).resolve().parents[1]
        / "shared"
        / "resources"
        / path.removeprefix(prefix)
    )


def _read_lines(path: str, *, encoding: str = "utf-8") -> list[str]:
    """
    Read lines from Qt resource (:/...).
    Returns a list of lines including newlines.
    """
    file = QFile(path)
    if file.open(QFile.ReadOnly | QFile.Text):  # type: ignore[attr-defined]
        stream = QTextStream(file)
        stream.setCodec(encoding)
        text = stream.readAll()
        file.close()
        return text.splitlines(keepends=True)

    # Standalone runs do not automatically register the compiled Qt resources.
    fallback_path = _resource_fallback_path(path)
    if fallback_path and fallback_path.is_file():
        return fallback_path.read_text(encoding=encoding).splitlines(keepends=True)

    raise FileNotFoundError(f"Could not open template resource: {path}")


def _apply_replacements(lines: list[str], mapping: dict[str, str]) -> list[str]:
    # replaces each placeholder everywhere
    return [_replace_many(line, mapping) for line in lines]


def _replace_many(s: str, mapping: dict[str, str]) -> str:
    for old, new in mapping.items():
        s = s.replace(old, new)
    return s


def _write_lines(path: Path, lines: list[str], *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=encoding, newline="\n") as f:
        f.writelines(lines)


def write_python_script(
    file_path: Path,
    script: str = "process",
    overwrite: dict | None = None,
) -> None:
    # read + apply replacements
    lines = _read_lines(f":/default_files/scripts/{script}.txt", encoding="utf-8")
    if overwrite:
        lines = _apply_replacements(lines, overwrite)
    _write_lines(file_path, lines)

    # --- 2. Try formatting with Black ---
    try:
        # join as crude code
        raw_code = "".join(lines)
        mode = black.FileMode()
        formatted_code = black.format_str(raw_code, mode=mode)
        file_path.write_text(formatted_code, encoding="utf-8")
    except Exception as e:
        logger.error(f"[WARN] Black formatting failed, crude version kept: {e}")


if __name__ == "__main__":
    write_python_script(
        Path("test.py"),
        script="process",
        overwrite={
            "---PROJECT_NAME---": "Test Project",
            "---PROCESS_NAME---": "Test Process",
            "---CLASS_NAME---": "TestClass",
            "---PROCESS_LABEL---": "Test Process Label",
            "---PROCESS_DESCRIPTION---": "Test Process Description",
        },
    )
