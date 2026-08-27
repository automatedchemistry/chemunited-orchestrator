# Installation

## Requirements

- Python >= 3.11

## Installation

```bash
git clone https://github.com/automatedchemistry/chemunited-workflow.git
cd chemunited-workflow

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Package, including FastAPI, MCP, and tray launcher support
pip install -e .

# With test dependencies
pip install -e ".[test]"

# With LAN advertisement (mDNS/Zeroconf)
pip install -e ".[discovery]"
```

---

[← Back to README](../README.md)
