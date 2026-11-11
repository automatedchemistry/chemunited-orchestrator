# 📘 Chemunited-Docs

This repository contains **only the documentation** for the [Chemunited](https://github.com/automatedchemistry/chemunited) package.
The main package (including source code, examples, and releases) is available in the Chemunited repository linked above.

---

## 📖 Access the Documentation

You can explore the full documentation online here:
👉 **[Chemunited Documentation on Read the Docs](https://chemunited-docs.readthedocs.io/en/latest/)**

---

## 🧠 About

This documentation is built with [Sphinx](https://www.sphinx-doc.org/) and [Read the Docs](https://readthedocs.org/).

## Build locally on Windows

From the repository root, use the existing project virtual environment in `.venv`:

```powershell
uv pip install --python .venv\Scripts\python.exe -r docs-site\requirements.txt
.\.venv\Scripts\python.exe -m sphinx -b html docs-site\docs docs-site\docs\_build\html
```

Open the generated documentation with:

```powershell
Start-Process docs-site\docs\_build\html\index.html
```
