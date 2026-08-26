@echo off
setlocal enabledelayedexpansion

echo ============================================
echo  ChemUnited Installer -- Windows only
echo ============================================
echo.
echo This installer does not support macOS or Linux.
echo.

set "INSTALL_DIR=%LOCALAPPDATA%\ChemUnited"
set "VENV_DIR=%INSTALL_DIR%\.venv"

if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"

:: 1. Ensure uv is available (installs to the current user's own folder --
::    no admin rights required, and safe to skip if already present).
where uv >nul 2>nul
if errorlevel 1 (
    echo Installing the uv package manager...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 (
        echo.
        echo Failed to install uv. See https://docs.astral.sh/uv/getting-started/installation/
        pause
        exit /b 1
    )
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
)

:: 2. uv manages its own isolated Python install -- no system Python needed.
echo Setting up Python...
uv python install 3.13
if errorlevel 1 (
    echo.
    echo Failed to install Python via uv.
    pause
    exit /b 1
)

:: 3. Create the venv and install ChemUnited from PyPI (re-running this
::    installer later will upgrade an existing install to the latest release).
echo Installing ChemUnited, this can take a few minutes...
uv venv "%VENV_DIR%" --python 3.13
if errorlevel 1 (
    echo.
    echo Failed to create the virtual environment.
    pause
    exit /b 1
)

uv pip install --python "%VENV_DIR%\Scripts\python.exe" --upgrade chemunited
if errorlevel 1 (
    echo.
    echo Failed to install ChemUnited.
    pause
    exit /b 1
)

:: 4. Build the launcher .bat and Desktop shortcut.
echo Creating launcher and shortcut...
"%VENV_DIR%\Scripts\chemunited-install-launcher.exe"
if errorlevel 1 (
    echo.
    echo Failed to create the launcher and shortcut.
    pause
    exit /b 1
)

echo.
echo Done! A "ChemUnited" shortcut has been added to your Desktop.
pause
exit /b 0
