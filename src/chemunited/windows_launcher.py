from __future__ import annotations

import os
import subprocess  # nosec B404 - used only to run a fixed, hardcoded PowerShell command below
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LAUNCHER_NAME = "chemunited.bat"
SHORTCUT_NAME = "ChemUnited.lnk"
ICON_PATH = (
    PROJECT_ROOT
    / "src"
    / "chemunited"
    / "shared"
    / "resources"
    / "icons"
    / "chemunited.ico"
)
COMMAND_EXECUTABLES = ("chemunited.exe",)
REQUIRED_EXECUTABLES = (
    "pythonw.exe",
    *COMMAND_EXECUTABLES,
)

_SHORTCUT_ENV = {
    "shortcut": "CHEMUNITED_SHORTCUT_PATH",
    "launcher": "CHEMUNITED_LAUNCHER_PATH",
    "working_directory": "CHEMUNITED_WORKING_DIRECTORY",
    "icon": "CHEMUNITED_ICON_PATH",
}
_CREATE_SHORTCUT_SCRIPT = """
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($env:CHEMUNITED_SHORTCUT_PATH)
$shortcut.TargetPath = $env:CHEMUNITED_LAUNCHER_PATH
$shortcut.WorkingDirectory = $env:CHEMUNITED_WORKING_DIRECTORY
$shortcut.IconLocation = $env:CHEMUNITED_ICON_PATH + ',0'
$shortcut.Description = 'ChemUnited Orchestrator'
$shortcut.Arguments = ''
$shortcut.Save()
""".strip()


class LauncherBuildError(Exception):
    def __init__(self, missing_paths: list[Path]) -> None:
        self.missing_paths = missing_paths
        super().__init__("Required launcher files are missing")


class ShortcutBuildError(Exception):
    pass


def resolve_venv_dir(venv_dir: Path, project_root: Path) -> Path:
    if not venv_dir.is_absolute():
        venv_dir = project_root / venv_dir
    return venv_dir.resolve()


def resolve_pythonw_path(venv_dir: Path) -> Path:
    scripts_pythonw = venv_dir / "Scripts" / "pythonw.exe"
    root_pythonw = venv_dir / "pythonw.exe"
    if scripts_pythonw.is_file() or not root_pythonw.is_file():
        return scripts_pythonw
    return root_pythonw


def find_missing_paths(project_root: Path, venv_dir: Path) -> list[Path]:
    candidates = [
        resolve_pythonw_path(venv_dir),
        *(venv_dir / "Scripts" / name for name in COMMAND_EXECUTABLES),
    ]
    return [path for path in candidates if not path.is_file()]


def _batch_path(path: Path) -> str:
    return str(path).replace("/", "\\").replace("%", "%%")


def _venv_reference(venv_dir: Path, project_root: Path) -> str:
    try:
        relative_dir = venv_dir.relative_to(project_root)
    except ValueError:
        return _batch_path(venv_dir)

    if relative_dir == Path("."):
        return r"%~dp0"
    return rf"%~dp0{_batch_path(relative_dir)}"


def render_launcher(project_root: Path, venv_dir: Path) -> bytes:
    venv_reference = _venv_reference(venv_dir, project_root)
    pythonw_path = resolve_pythonw_path(venv_dir)
    if pythonw_path.parent == venv_dir / "Scripts":
        pythonw_reference = r"%SCRIPTS_DIR%\pythonw.exe"
    else:
        pythonw_reference = r"%VENV_DIR%\pythonw.exe"
    executable_checks = "\r\n".join(
        line
        for name in COMMAND_EXECUTABLES
        for line in (
            f'if not exist "%SCRIPTS_DIR%\\{name}" (',
            f'    echo Missing required executable: "%SCRIPTS_DIR%\\{name}"',
            '    set "LAUNCHER_MISSING=1"',
            ")",
        )
    )
    lines = [
        "@echo off",
        "setlocal",
        "",
        'set "PROJECT_DIR=%~dp0"',
        f'set "VENV_DIR={venv_reference}"',
        'set "SCRIPTS_DIR=%VENV_DIR%\\Scripts"',
        f'set "PYTHONW={pythonw_reference}"',
        'set "LAUNCHER_MISSING="',
        "",
        'if not exist "%PYTHONW%" (',
        '    echo Missing required executable: "%PYTHONW%"',
        '    set "LAUNCHER_MISSING=1"',
        ")",
        executable_checks,
        "",
        "if defined LAUNCHER_MISSING (",
        "    echo.",
        "    echo Regenerate this launcher after creating or updating the virtual environment.",
        "    pause",
        "    exit /b 1",
        ")",
        "",
        'set "PATH=%SCRIPTS_DIR%;%PATH%"',
        'cd /d "%PROJECT_DIR%"',
        'start "" "%PYTHONW%" -m chemunited %*',
        "exit /b 0",
        "",
    ]
    return "\r\n".join(lines).encode("utf-8")


def build_launcher(project_root: Path, venv_dir: Path) -> Path:
    project_root = project_root.resolve()
    venv_dir = resolve_venv_dir(venv_dir, project_root)
    missing_paths = find_missing_paths(project_root, venv_dir)
    if missing_paths:
        raise LauncherBuildError(missing_paths)

    launcher_path = project_root / LAUNCHER_NAME
    launcher_path.write_bytes(render_launcher(project_root, venv_dir))
    return launcher_path


def create_windows_shortcut(
    shortcut_path: Path,
    launcher_path: Path,
    icon_path: Path,
    working_directory: Path,
) -> Path:
    shortcut_path = shortcut_path.resolve()
    launcher_path = launcher_path.resolve()
    icon_path = icon_path.resolve()
    working_directory = working_directory.resolve()

    missing_paths = [path for path in (launcher_path, icon_path) if not path.is_file()]
    if not shortcut_path.parent.is_dir():
        missing_paths.append(shortcut_path.parent)
    if not working_directory.is_dir():
        missing_paths.append(working_directory)
    if missing_paths:
        missing = "\n".join(f"  - {path}" for path in missing_paths)
        raise ShortcutBuildError(f"Required shortcut paths are missing:\n{missing}")

    environment = os.environ.copy()
    environment.update(
        {
            _SHORTCUT_ENV["shortcut"]: str(shortcut_path),
            _SHORTCUT_ENV["launcher"]: str(launcher_path),
            _SHORTCUT_ENV["working_directory"]: str(working_directory),
            _SHORTCUT_ENV["icon"]: str(icon_path),
        }
    )
    command = [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        _CREATE_SHORTCUT_SCRIPT,
    ]

    try:
        result = subprocess.run(  # nosec B603 - command list is static; dynamic values are passed via env, not argv
            command,
            capture_output=True,
            text=True,
            check=False,
            env=environment,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as error:
        raise ShortcutBuildError(f"Could not start PowerShell: {error}") from error

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        if not detail:
            detail = f"PowerShell exited with code {result.returncode}"
        raise ShortcutBuildError(detail)
    if not shortcut_path.is_file():
        raise ShortcutBuildError(
            f"PowerShell completed without creating {shortcut_path}"
        )

    return shortcut_path
