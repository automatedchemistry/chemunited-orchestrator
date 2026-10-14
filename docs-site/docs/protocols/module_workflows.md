# Process workflow

A process is built as a workflow made of multiple modules.
The workflow controls how modules are executed, handling:

* parallel execution

* conditions (branching)

* loops (repetition)

This keeps control logic outside individual modules (sometimes called blocks), so each module stays focused on a single task.

## Module Types

There are five kinds of modules.

* <img src="../_static/icons/python.svg" width="16" style="vertical-align:middle; margin-right:4px;"> Script

A Script module contains the actual commands to run.
Use it to define the step-by-step actions of your protocol.

* <img src="../_static/icons/block_for_black.svg" width="16" style="vertical-align:middle; margin-right:4px;"> Loop

A Loop module repeats one or more modules.
Use it when a part of the protocol must run multiple times (for example: iterating over modules or repeating a some step).

* <img src="../_static/icons/block_if_black.svg" width="16" style="vertical-align:middle; margin-right:4px;"> Conditional

A Conditional module creates a branching point in the workflow.
Depending on the defined criteria, the process follows one branch or another.

* <img src="../_static/icons/play_black.svg" width="16" style="vertical-align:middle; margin-right:4px;"> Command

A Command module represents a single command sent to one associated device — no code required. Rather than
clicking New Module, you drag it directly onto the canvas from the
[Command List](build_protocols.md#command-list).

* <img src="../_static/icons/update_black.svg" width="16" style="vertical-align:middle; margin-right:4px;"> Background

A Background module is a Script that runs alongside the rest of the protocol. It has an input but no output, so
nothing waits for it: the process continues, and the protocol moves on to the next processes while it keeps running.
It stops when the protocol stops. See [Background modules](#background-modules).

## Why use workflows?

Technically, you can implement loops and conditionals inside a single Script module using Python packages and native functions.
However, we recommend using the workflow approach because it makes protocols:

* easier to read and maintain

* more modular and reusable

* better structured (logic is explicit in the workflow)

## Example

<img src="../_static/workflow_example.png" width="900px">

In the example above, you can follow how the workflow is executed:

**1) Parallel execution (fan-out)**

After *script 1*, *2*, and *4*, the workflow splits into multiple branches.
This means the next connected modules can run in parallel (when they are independent).

**2) Loop execution**

The module *loop_1* repeats a part of the workflow.
In this example, it triggers the repeated execution of the branch that starts at *script 2*.

**3) Conditional execution (branching)**

The module *conditional_1* chooses one branch based on the condition criteria.
Here, it selects between the branch starting at *command 3* or *4*.

**4) Synchronization (wait / join)**

Some modules only start when all required input branches have finished.
For example, *script 11* waits until every incoming branch completes before it begins execution.

**5) Command modules**

The *command* blocks (*command_1* through *command_6*) are Command modules — each one sends a single command to
an associated device and was dragged directly onto the canvas from the [Command List](build_protocols.md#command-list),
rather than written as a Script.

## Background modules

Use a Background module for work that should run during the whole protocol, such as requesting data from an
analytical instrument or processing a signal.

```
start ──▶ script_1 ──▶ end
  │
  └──▶ background_1        (dashed block, input only)
```

Here *background_1* starts together with *script_1*. When *script_1* reaches *end*, the process is finished and the
protocol continues with the next process, while *background_1* keeps running. It stops when the protocol finishes,
fails, or is cancelled.

A new Background module starts from this template:

```python
def background_1(self, ctx: NodeExecutionContext) -> bool:
    # Runs alongside the rest of the protocol; stops when it ends.
    while not ctx.stop_requested:
        # Read instruments, process signals, ctx.report_progress(...)
        self.platform._wait(5)  # wakes immediately on stop
    return True
```

* Keep the `while not ctx.stop_requested:` loop, and wait with `self.platform._wait(...)` rather than `time.sleep(...)`,
  so the module stops as soon as the protocol does. When the protocol ends, the run waits up to 10 seconds for
  background modules to stop.
* Don't send commands to a device that the rest of the protocol also uses. Two modules can't use the same device at
  the same time.
* If a Background module fails, the error is logged and shown on its row, but the protocol keeps running.
* If a Background module sits inside a loop, a new copy starts on every iteration.

## Building a module

To create a new Script, Loop, Conditional, or Background module, use the matching action in the
[workflow canvas menu](build_protocols.md#workflow-canvas-menu) — **Add Script**, **Add Loop**, **Add Conditional**, or
**Add Background**.

### Saving

When you click Save, the script is stored automatically in the project directory using this structure:

```
...\ <project_folder> \ protocols \ <process_name>.py
```
