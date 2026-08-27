# Examples

The repository includes one full demonstration and one generated ChemUnited
Draw project.

## `examples/full_platform.py`

Run it from the repository root:

```powershell
.\.venv\Scripts\python.exe tests\flow_platform
```

This example demonstrates:

- Gas and liquid phases.
- Pressure controllers and a flow source.
- Plug-flow transport tubes.
- A pressurised vessel reactor.
- A back-pressure regulator.
- A junction mixer.
- A two-position divert valve.
- First-order reaction chemistry.
- SQLite recording and simple printed summaries.

The companion diagram is:

```text
examples/full_platform_flow_diagram.svg
```

The example writes a timestamped SQLite database under `examples/simulation/`.

## `examples/complete/draw/setup.py`

This file is generated from a ChemUnited Draw canvas. It rebuilds the platform
layout with `build_draw(platform)` and is useful as a larger real-world
platform fixture.

The corresponding exported drawing is:

```text
examples/complete/draw/platform.svg
```
