# Install ChemUnited

ChemUnited is available on PyPI as the `chemunited` package, and its source is hosted on GitHub.

## Install from PyPI (recommended)

```shell
pip install chemunited
```

## Install the latest development version (GitHub)

If you want the most recent changes that may not yet be published on PyPI, install directly from GitHub:

```shell
pip install git+https://github.com/automatedchemistry/chemunited-orchestrator.git
```
<div class="info-block">
  <strong>💡 Tip</strong><br>
  We recommend installing ChemUnited inside a virtual environment (venv/conda) to avoid
  conflicts with other Python packages.
</div>

## Updating ChemUnited

ChemUnited is under active development (e.g., new components and features are added over time).
To update your installation, run:

```shell
pip install chemunited --upgrade
```

## Create a Desktop Shortcut (Windows)

Once ChemUnited is installed, you can generate a Windows shortcut so you don't have to activate
the virtual environment and type a command every time you want to launch it.

1. Launch ChemUnited as usual (`chemunited`, or `python -m chemunited`).
2. Open the **Project** menu and click **Create Desktop Shortcut...**.
3. Pick a destination folder in the dialog that appears — your Desktop, the Start Menu, or any
   other folder. The dialog opens on your Desktop by default.

This creates two files:

- A `chemunited.bat` launcher next to your ChemUnited installation, which starts the app with
  `pythonw.exe` (no console window) from the Python environment you're currently running in.
- A shortcut (`ChemUnited.lnk`) at the folder you picked, pointing at that launcher and using the
  ChemUnited application icon.

<div class="info-block">
  <strong>💡 Tip</strong><br>
  If a shortcut already exists at the chosen location, ChemUnited asks before replacing it.
</div>

<div class="info-block">
  <strong>💡 Tip</strong><br>
  This feature is Windows-only — the menu item is hidden on other platforms. If you reinstall
  ChemUnited into a different virtual environment, regenerate the shortcut so it points at the
  new environment.
</div>
