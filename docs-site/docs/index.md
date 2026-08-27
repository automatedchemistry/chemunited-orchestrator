# 🌟 Welcome to Chemunited

```{raw} html
:file: _templates/custom_logo.html
```

## 🚀 Overview

**ChemUnited** provides a user-friendly, visual interface for designing and executing complex lab automation 
workflows. It enables researchers, chemists, and automation engineers to construct, simulate, and monitor experiments through
an intuitive GUI without writing extensive code.

This project is ideal for controlling platform chemistry setups, especially when real-time interaction and visual protocol
design are needed.

---

## 🧠 Features

- 🎛️ **Visual Process Builder**: Drag-and-drop UI to define processes, modules, and steps.
- 🔗 **Connection Graphs**: Manage and visualize physical and logical device connections.
- ⚙️ **Protocol Execution Engine**: Run and monitor experiments in real time.
- 📈 **Timeline Monitoring**: See process evolution and status updates at every stage.
- 🧬 **FlowChem Integration**: Deep integration with [FlowChem](https://github.com/cambiegroup/flowchem)
to control physical hardware.
- 💡 **Modular Architecture**: Built using PyQt with pluggable component support.

---

## How to start

New to ChemUnited? Follow this path:

1. **[Install ChemUnited](wellcome/install.md)** — set up the package and launch the Designer.
2. **[Create a new project](wellcome/new_project.md)** — start the Designer and set up your project folder.
3. **[Draw your setup](drawing/drawing.md)** — lay out your platform and its connections.
4. **[Build protocols](protocols/build_protocols.md)** — define the processes and workflow logic.
5. **[Connect your devices](connectivity/connectivity.md)** — link the drawing to physical hardware.
6. **[Run and monitor](monitoring/run_monitoring.md)** — execute protocols and track experiments live.

Prefer a hands-on walkthrough? Start with the **[Drawing Tutorial](tutorials/drawing_tutorial.md)**.

---

## 🧭 Table of Contents

```{toctree}
:maxdepth: 1
:caption: Install and Setting Up

wellcome/install.md
wellcome/new_project.md

```

```{toctree}
:maxdepth: 1
:caption: Design and Test
drawing/drawing.md
protocols/build_protocols.md
protocols/module_workflows.md
protocols/command.md
protocols/script_editor.md
protocols/parameters.md
simulation/digital_twins.md
connectivity/connectivity.md
protocols/pre_running.md
```

```{toctree}
:maxdepth: 1
:caption: Execute and Monitoring
monitoring/run_monitoring.md
```

```{toctree}
:maxdepth: 1
:caption: Dashboard
dashboard/launcher.md
dashboard/overview.md
dashboard/run_control.md
dashboard/protocols.md
dashboard/monitoring.md
dashboard/logs.md
dashboard/devices.md
dashboard/api_and_mcp.md
```

```{toctree}
:maxdepth: 1
:caption: Reference

reference/components.md
```

```{toctree}
:maxdepth: 1
:caption: Tutorial
tutorials/drawing_tutorial.md
tutorials/protocols_tutorial.md
tutorials/monitoring_tutorial.md
tutorials/connectivity_tutorial.md
```

```{toctree}
:maxdepth: 1
:caption: Developer

developer/welcome.md
developer/software_design.md
developer/component_concepts.md
developer/add_components.md
developer/add_features.md
developer/customize_dashboard.md
developer/backend.md
```

---

## 📄 License

This project is licensed under the **MIT License**.

---

## 👨‍🔬 Author & Repository link

**Samuel Saraiva**

Max Planck Institute of Colloids and Interfaces - Automated Chemistry Group

```{raw} html
<a href="https://github.com/automatedchemistry/chemunited" target="_blank" style="text-decoration:none;">
  <img src="_static/icons/github.svg" alt="GitHub" width="28" style="vertical-align:middle; margin-right:6px;">
  <strong>View ChemUnited on GitHub</strong>
</a>
```

📧 samuel.saraiva@mpikg.mpg.de




