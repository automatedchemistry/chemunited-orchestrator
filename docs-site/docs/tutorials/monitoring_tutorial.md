# 6. Run the dashboard

Continue from [5. Connect the devices](connectivity_tutorial.md) with the project saved and
its device server running. This step adds the desktop process **Process** to a browser
protocol named **tutorial_transfer**, runs it, and follows its execution cards.

```{image} ../_static/tutorials/06-dashboard.gif
:alt: Launching the dashboard, saving tutorial_transfer, and watching execution cards beside synchronized footage of the physical pump and valve.
:width: 100%
```

During execution, the GIF shows the supplied hardware recording beside the **Process Execution** cards. The footage plays at real speed, following selection of valve port **4** for A, withdrawal, selection of port **16** for B, and infusion. It is labeled **Recorded hardware execution**.

The dashboard replay uses the temporary local demonstration devices from step 5. To follow the
same sequence with hardware, use your own running FlowChem server and saved associations
as described in [Setup Connectivity](../connectivity/connectivity.md).

## Launch and assemble the protocol

1. In the desktop app, open **Run** and click **Launch Dashboard**. Wait for the status to
   become **Running**, then continue in the browser. The dashboard loads the project saved
   on disk; see [Dashboard Launcher](../dashboard/launcher.md).
2. Open **Protocols**. Select **Process** under **Available processes** and click
   **Add to protocol**.
3. Set **Protocol name** to `tutorial_transfer` and click **Save protocol**. This creates a
   timestamped `tutorial_transfer_<timestamp>.json` file in the project's protocol history.

See [Protocols](../dashboard/protocols.md) for assembling longer sequences.

## Start and watch the execution cards

1. Open **Configurations**. Leave **Dry run**, **Error-resilient mode** and
   **Record monitoring data** unchecked.
   Enable **Dry run** instead when you want to check the workflow without sending device
   commands. See [Run options](../dashboard/configurations.md#run-control).
2. Open **Run Control** and select the saved `tutorial_transfer_<timestamp>.json` file.
3. Scroll down to **Process Execution** to see the process card's **waiting** state.
4. Return to the controls and click **Start Protocol**, then scroll down to **Process
   Execution** again. Keep the cards in view to follow the **running** state and the node
   progress bars alongside the hardware footage.
5. Wait for the process card to show **completed** and the successful nodes to reach
   **100%**. The system state also reports **Protocol completed successfully.**
6. Open **Dashboard** to return to the platform overview.

The demonstration selects vessel A, withdraws **0.5 mL at 1 mL/min**, selects vessel B,
and infuses the same volume. The process cards show the execution of those commands;
see [Run Control](../dashboard/run_control.md) for the controls and status display.

Previous: [5. Connect the devices](connectivity_tutorial.md) · Next: [Monitoring](../dashboard/monitoring.md)
