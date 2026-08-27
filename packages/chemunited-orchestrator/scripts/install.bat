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

:: 1. Ensure uv is available. Preference order:
::      a) already on PATH
::      b) `pip install --user uv` via any system Python -- this goes
::         through the same PyPI channel the rest of this installer already
::         needs, so it's far more likely to be allowed under a restrictive
::         IT policy than downloading and running an arbitrary script
::      c) the official installer script, only if no system Python exists
::         to bootstrap uv via pip in the first place
set "UV_CMD=uv"

where uv >nul 2>nul
if errorlevel 1 (
    set "UV_CMD="
    where python >nul 2>nul
    if not errorlevel 1 (
        echo No system-wide uv found; installing it via pip instead...
        python -m pip install --user --upgrade uv >nul
        if not errorlevel 1 (
            :: Invoke through `python -m uv` rather than searching PATH for
            :: the console-script wrapper pip just installed -- its exact
            :: location varies across Python/pip versions, but `python -m uv`
            :: always works once the uv package itself is importable.
            set "UV_CMD=python -m uv"
        )
    )
)

if not defined UV_CMD (
    echo Installing the uv package manager...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    if errorlevel 1 (
        echo.
        echo Failed to install uv. See https://docs.astral.sh/uv/getting-started/installation/
        pause
        exit /b 1
    )
    set "PATH=%USERPROFILE%\.local\bin;%PATH%"
    set "UV_CMD=uv"
)

:: 2. uv manages its own isolated Python install -- no system Python needed.
echo Setting up Python...
%UV_CMD% python install 3.13
if errorlevel 1 (
    echo.
    echo Failed to install Python via uv.
    pause
    exit /b 1
)

:: 3. Create the venv and install ChemUnited from PyPI (re-running this
::    installer later will upgrade an existing install to the latest release).
echo Installing ChemUnited, this can take a few minutes...
%UV_CMD% venv "%VENV_DIR%" --python 3.13
if errorlevel 1 (
    echo.
    echo Failed to create the virtual environment.
    pause
    exit /b 1
)

%UV_CMD% pip install --python "%VENV_DIR%\Scripts\python.exe" --upgrade chemunited
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
