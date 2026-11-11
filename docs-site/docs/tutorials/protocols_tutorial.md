# 3. Build the protocol

Continue from [2. Add a substance and fill the vessel](inventory_tutorial.md). The setup contains vessels **A** and **B**, **valve**, **Loop**, and syringe pump **P01**; A starts with 10 mL of ethanol.

Create a process called **Process** with four command blocks. These commands select A, withdraw liquid, select B, and infuse liquid. You will add this process to a dashboard protocol in [step 6](monitoring_tutorial.md).

```{image} ../_static/tutorials/03-build-protocol.gif
:alt: Creating Process, dragging valve and pump commands onto the workflow, editing their parameters and compact labels, and connecting the blocks in order.
:width: 100%
```

## Create the process

Open the desktop app's **Protocol** step. Open the process list and click **New Process**. The new process is named **Process** in this example and contains **Start** and **End** nodes.

Move the nodes apart to leave space for the four commands, then open the **Command List**.

## Add and configure the commands

Find each device and command in the Command List, using the search field when needed, and drag its row onto the workflow canvas. Double-click the new block to open its command editor.

Configure the four blocks in this order. Set both the compact **Label** and the full **Description**, then click **Save** in each editor.

| Label | Device and command | Parameters | Description |
| --- | --- | --- | --- |
| **A** | `valve` → `position` | Connect ports `[[0, 4]]` | Select vessel A using valve port 4 |
| **In** | `P01` → `withdraw` | Volume **0.5 mL**<br>Rate **1 mL/min** | Withdraw 0.5 mL at 1 mL/min |
| **B** | `valve` → `position` | Connect ports `[[0, 16]]` | Select vessel B using valve port 16 |
| **Out** | `P01` → `infuse` | Volume **0.5 mL**<br>Rate **1 mL/min** | Infuse 0.5 mL at 1 mL/min |

The canvas also shows each block's generated identifier, such as `command_1`, beside its label. The short labels keep the graph readable, while the descriptions retain the full action and quantities.

## Connect and save the workflow

Click a block's output port, then the next block's input port, to form this sequence:

**Start → A → In → B → Out → End**

Keep the default `condition=true` connections shown in the recording. Click **Save** on the Protocol page to save the process and its configured commands.

For more detail, see [Command blocks](../protocols/command.md), [Process workflows](../protocols/module_workflows.md), and the [protocol hierarchy](../protocols/build_protocols.md).

[← Previous: Add a substance and fill the vessel](inventory_tutorial.md) · [Next: Simulate the process →](simulation_tutorial.md)
