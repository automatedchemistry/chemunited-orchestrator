import sys
from pathlib import Path
from subprocess import CompletedProcess

import pytest

import chemunited.windows_launcher as windows_launcher
from chemunited.windows_launcher import (
    COMMAND_EXECUTABLES,
    LAUNCHER_NAME,
    REQUIRED_EXECUTABLES,
    LauncherBuildError,
    ShortcutBuildError,
    build_launcher,
    create_windows_shortcut,
)


def create_project(project_root: Path, venv_dir: Path) -> None:
    project_root.mkdir(parents=True)
    scripts_dir = venv_dir / "Scripts"
    scripts_dir.mkdir(parents=True)
    for executable in REQUIRED_EXECUTABLES:
        (scripts_dir / executable).write_bytes(b"")


def test_build_launcher_uses_project_relative_default_venv(tmp_path):
    project_root = tmp_path / "project with spaces"
    venv_dir = project_root / ".venv"
    create_project(project_root, venv_dir)

    launcher_path = build_launcher(project_root, Path(".venv"))

    assert launcher_path == project_root / LAUNCHER_NAME
    raw_launcher = launcher_path.read_bytes()
    launcher = raw_launcher.decode("utf-8")
    assert 'set "VENV_DIR=%~dp0.venv"' in launcher
    assert 'set "PATH=%SCRIPTS_DIR%;%PATH%"' in launcher
    assert 'cd /d "%PROJECT_DIR%"' in launcher
    assert 'set "PYTHONW=%SCRIPTS_DIR%\\pythonw.exe"' in launcher
    assert 'start "" "%PYTHONW%" -m chemunited %*' in launcher
    assert b"\r\n" in raw_launcher
    assert b"\n" not in raw_launcher.replace(b"\r\n", b"")


def test_build_launcher_uses_relative_custom_venv_inside_project(tmp_path):
    project_root = tmp_path / "project"
    venv_dir = project_root / "environments" / "chemunited env"
    create_project(project_root, venv_dir)

    launcher_path = build_launcher(
        project_root, Path("environments") / "chemunited env"
    )

    launcher = launcher_path.read_text(encoding="utf-8")
    assert 'set "VENV_DIR=%~dp0environments\\chemunited env"' in launcher


def test_build_launcher_uses_absolute_external_venv(tmp_path):
    project_root = tmp_path / "project"
    venv_dir = tmp_path / "external venv"
    create_project(project_root, venv_dir)

    launcher_path = build_launcher(project_root, venv_dir)

    launcher = launcher_path.read_text(encoding="utf-8")
    expected_venv = str(venv_dir.resolve()).replace("/", "\\").replace("%", "%%")
    assert f'set "VENV_DIR={expected_venv}"' in launcher


def test_build_launcher_supports_base_python_layout(tmp_path):
    project_root = tmp_path / "project"
    environment_dir = tmp_path / "base python"
    create_project(project_root, environment_dir)
    (environment_dir / "Scripts" / "pythonw.exe").unlink()
    (environment_dir / "pythonw.exe").write_bytes(b"")

    launcher_path = build_launcher(project_root, environment_dir)

    launcher = launcher_path.read_text(encoding="utf-8")
    assert 'set "PYTHONW=%VENV_DIR%\\pythonw.exe"' in launcher
    assert 'start "" "%PYTHONW%" -m chemunited %*' in launcher


def test_build_launcher_reports_every_missing_file_without_overwriting(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    launcher_path = project_root / LAUNCHER_NAME
    launcher_path.write_text("existing launcher", encoding="utf-8")
    venv_dir = project_root / ".venv"

    with pytest.raises(LauncherBuildError) as error_info:
        build_launcher(project_root, venv_dir)

    assert error_info.value.missing_paths == [
        venv_dir / "Scripts" / name for name in REQUIRED_EXECUTABLES
    ]
    assert launcher_path.read_text(encoding="utf-8") == "existing launcher"


def test_generated_launcher_checks_required_files_at_runtime(tmp_path):
    project_root = tmp_path / "project"
    venv_dir = project_root / ".venv"
    create_project(project_root, venv_dir)

    launcher = build_launcher(project_root, venv_dir).read_text(encoding="utf-8")

    assert 'if not exist "%PYTHONW%"' in launcher
    for executable in COMMAND_EXECUTABLES:
        assert f'if not exist "%SCRIPTS_DIR%\\{executable}"' in launcher
    assert "pause" in launcher
    assert "exit /b 1" in launcher


def create_shortcut_inputs(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    destination = tmp_path / "shortcut destination & spaces"
    destination.mkdir()
    working_directory = tmp_path / "project with spaces"
    working_directory.mkdir()
    launcher_path = working_directory / "chemunited.bat"
    launcher_path.write_bytes(b"@echo off\r\n")
    icon_path = working_directory / "chemunited icon.ico"
    icon_path.write_bytes(b"icon")
    shortcut_path = destination / "ChemUnited.lnk"
    return shortcut_path, launcher_path, icon_path, working_directory


def test_create_windows_shortcut_passes_fields_safely_via_environment(
    tmp_path, monkeypatch
):
    shortcut_path, launcher_path, icon_path, working_directory = create_shortcut_inputs(
        tmp_path
    )
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        Path(kwargs["env"]["CHEMUNITED_SHORTCUT_PATH"]).write_bytes(b"shortcut")
        return CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(windows_launcher.subprocess, "run", fake_run)

    result = create_windows_shortcut(
        shortcut_path,
        launcher_path,
        icon_path,
        working_directory,
    )

    assert result == shortcut_path.resolve()
    command = captured["command"]
    kwargs = captured["kwargs"]
    assert command[:5] == [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
    ]
    assert str(shortcut_path.resolve()) not in command[-1]
    assert kwargs["env"]["CHEMUNITED_SHORTCUT_PATH"] == str(shortcut_path.resolve())
    assert kwargs["env"]["CHEMUNITED_LAUNCHER_PATH"] == str(launcher_path.resolve())
    assert kwargs["env"]["CHEMUNITED_WORKING_DIRECTORY"] == str(
        working_directory.resolve()
    )
    assert kwargs["env"]["CHEMUNITED_ICON_PATH"] == str(icon_path.resolve())
    assert kwargs["creationflags"] == getattr(
        windows_launcher.subprocess, "CREATE_NO_WINDOW", 0
    )


def test_create_windows_shortcut_reports_powershell_failure(tmp_path, monkeypatch):
    shortcut_path, launcher_path, icon_path, working_directory = create_shortcut_inputs(
        tmp_path
    )

    def fake_run(command, **_kwargs):
        return CompletedProcess(
            command,
            1,
            stdout="",
            stderr="WScript.Shell failed",
        )

    monkeypatch.setattr(windows_launcher.subprocess, "run", fake_run)

    with pytest.raises(ShortcutBuildError, match="WScript.Shell failed"):
        create_windows_shortcut(
            shortcut_path,
            launcher_path,
            icon_path,
            working_directory,
        )


def test_create_windows_shortcut_requires_created_output(tmp_path, monkeypatch):
    shortcut_path, launcher_path, icon_path, working_directory = create_shortcut_inputs(
        tmp_path
    )

    def fake_run(command, **_kwargs):
        return CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(windows_launcher.subprocess, "run", fake_run)

    with pytest.raises(ShortcutBuildError, match="completed without creating"):
        create_windows_shortcut(
            shortcut_path,
            launcher_path,
            icon_path,
            working_directory,
        )


def test_create_windows_shortcut_validates_required_paths(tmp_path):
    destination = tmp_path / "destination"
    destination.mkdir()

    with pytest.raises(ShortcutBuildError) as error_info:
        create_windows_shortcut(
            destination / "ChemUnited.lnk",
            tmp_path / "missing.bat",
            tmp_path / "missing.ico",
            tmp_path / "missing project",
        )

    message = str(error_info.value)
    assert "missing.bat" in message
    assert "missing.ico" in message
    assert "missing project" in message


def create_main_environment(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Wire up main()'s module-level globals to point inside tmp_path, so a
    test run never touches the real Desktop, venv, or installed icon."""
    project_root = tmp_path / "install"
    venv_dir = project_root / ".venv"
    create_project(project_root, venv_dir)

    home = tmp_path / "home"
    (home / "Desktop").mkdir(parents=True)
    icon_path = tmp_path / "chemunited.ico"
    icon_path.write_bytes(b"icon")

    monkeypatch.setattr(windows_launcher, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(windows_launcher, "ICON_PATH", icon_path)
    monkeypatch.setattr(windows_launcher.sys, "prefix", str(venv_dir))
    monkeypatch.setattr(windows_launcher.Path, "home", staticmethod(lambda: home))
    return project_root, home


def test_main_builds_launcher_and_desktop_shortcut(tmp_path, monkeypatch):
    project_root, home = create_main_environment(tmp_path, monkeypatch)

    def fake_run(command, **kwargs):
        Path(kwargs["env"]["CHEMUNITED_SHORTCUT_PATH"]).write_bytes(b"shortcut")
        return CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(windows_launcher.subprocess, "run", fake_run)

    exit_code = windows_launcher.main()

    assert exit_code == 0
    assert (project_root / LAUNCHER_NAME).is_file()
    assert (home / "Desktop" / windows_launcher.SHORTCUT_NAME).is_file()


def test_main_rejects_non_windows(monkeypatch):
    monkeypatch.setattr(windows_launcher.sys, "platform", "linux")

    assert windows_launcher.main() == 1


def test_main_reports_missing_launcher_files(tmp_path, monkeypatch):
    project_root = tmp_path / "install"
    project_root.mkdir()
    venv_dir = project_root / ".venv"
    venv_dir.mkdir()
    # No executables written under venv_dir/Scripts, so build_launcher fails.

    monkeypatch.setattr(windows_launcher, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(windows_launcher.sys, "prefix", str(venv_dir))

    assert windows_launcher.main() == 1
    assert not (project_root / LAUNCHER_NAME).exists()


def test_main_reports_shortcut_failure(tmp_path, monkeypatch):
    project_root, home = create_main_environment(tmp_path, monkeypatch)

    def fake_run(command, **_kwargs):
        return CompletedProcess(command, 1, stdout="", stderr="WScript.Shell failed")

    monkeypatch.setattr(windows_launcher.subprocess, "run", fake_run)

    assert windows_launcher.main() == 1
    # The launcher itself is still built even if the shortcut step fails.
    assert (project_root / LAUNCHER_NAME).is_file()
    assert not (home / "Desktop" / windows_launcher.SHORTCUT_NAME).exists()


def test_icon_path_points_at_bundled_chemunited_icon():
    assert windows_launcher.ICON_PATH.is_file()
    assert windows_launcher.ICON_PATH.name == "chemunited.ico"


def test_icon_path_is_resolved_relative_to_the_installed_package():
    # Must not depend on a "src" checkout layout, so it also works for a
    # non-editable pip install (package sits directly in site-packages).
    expected = (
        Path(windows_launcher.__file__).resolve().parent
        / "shared"
        / "resources"
        / "icons"
        / "chemunited.ico"
    )
    assert windows_launcher.ICON_PATH == expected


def test_project_root_is_resolved_relative_to_the_running_venv():
    assert windows_launcher.PROJECT_ROOT == Path(sys.prefix).parent
