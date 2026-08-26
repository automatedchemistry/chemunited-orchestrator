# Quick Start

### 1. Define a workflow

```python
from chemunited_workflow import Process, Platform
import networkx as nx
from pydantic import BaseModel

class MyConfig(BaseModel):
    volume_ul: float
    temperature_c: float

class MyWorkflow(Process[MyConfig]):
    def build_workflow(self) -> nx.DiGraph:
        G = nx.DiGraph()
        G.add_node("dispense",  method="dispense_step")
        G.add_node("heat",      method="heat_step")
        G.add_node("verify",    method="verify_step")
        G.add_edge("dispense",  "heat",   condition=True)
        G.add_edge("heat",      "verify", condition=True)
        return G

    def dispense_step(self, ctx):
        client = self.platform["pump_01"]
        r = client.post("dispense", json={"volume": self.config.volume_ul}, raw_response=True)
        return r.status_code == 200

    def heat_step(self, ctx):
        client = self.platform["reactor_01"]
        r = client.post("set_temp", json={"temp": self.config.temperature_c}, raw_response=True)
        return r.status_code == 200

    def verify_step(self, ctx):
        client = self.platform["reactor_01"]
        return client.get("status")["ready"]
```

Any node method can push live progress back to the dashboard while it's still running, via `ctx.report_progress(percentage, message)` — see [Concepts → Node Progress Feedback](concepts.md#node-progress-feedback). A node can also pause and wait for an operator to reply on the dashboard before continuing, via `ctx.request_operator_input(message, timeout_seconds)` — see [Concepts → Human-in-the-Loop Input](concepts.md#human-in-the-loop-input).

### 2. Configure device connectivity

Create `connectivity/associations.json`:

```json
{
  "server_url": "http://192.168.1.10",
  "associations": [
    { "component": "pump_01",    "component_url": "devices/pump_01" },
    { "component": "reactor_01", "component_url": "devices/reactor_01" }
  ]
}
```

### 3. Run the workflow

```python
from pathlib import Path

platform = Platform.from_project_dir(Path("my_project"))
config = MyConfig(volume_ul=500, temperature_c=60.0)
workflow = MyWorkflow(config, platform)
result = workflow.run_workflow(start_node="dispense")
print(result)
```

## Project Structure

A typical project using this library looks like:

```
my_project/
├── protocols/
│   ├── __init__.py              # PROCESSES and CONFIGS dicts
│   ├── main_parameters.py       # MainParameter Pydantic model
│   └── my_workflow.py           # Process subclasses (also readable via read_process)
├── connectivity/
│   └── associations.json        # Device URL mapping
├── protocols_historic/          # Versioned protocol files
├── log/                         # Execution logs
│   └── monitoring/              # Monitoring session profiles (one sub-dir per session_id)
└── ui/                          # Optional — custom UI templates (see Customising the UI)
    ├── templates/
    └── static/
```

`protocols/__init__.py` must export:

```python
from .my_workflow import MyWorkflow, MyConfig

PROCESSES = {"my_workflow": MyWorkflow}
CONFIGS   = {"my_workflow": MyConfig}
```

---

When you are ready to deploy, see [Deployment Modes](deployment.md).

[← Back to README](../README.md)
