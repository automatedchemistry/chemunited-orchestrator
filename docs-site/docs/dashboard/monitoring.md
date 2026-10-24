# Monitoring

<div class="warning-block">
<strong>⚠️ Not the same as the Monitor window</strong><br>
This page polls arbitrary device variables on demand, independent of any run. It is a different feature from the
desktop orchestrator's <a href="../monitoring/run_monitoring.md">Monitor window</a>, which watches a protocol
<em>while it executes</em>. Use this page to observe equipment state at any time; use
<a href="run_control.md">Run Control</a> and the Monitor window to watch an actual run.
</div>

**Monitoring** lets you poll live values from any connected device — useful for watching equipment state before,
between, or independently of runs (e.g. keeping an eye on a temperature reading while you set up a platform by
hand).

![Alt text](../_static/dashboard_monitoring.png)

## Session Config

| Field | Description |
|---|---|
| **Sample Time** | How often (in seconds) each variable is polled. |
| **Request Timeout** | How long to wait for a device to respond before treating that poll as failed. |
| **Component** | The device to read from. |
| **Get Variable** | Which of that device's `GET` commands to poll. |

Click **Add Variable** to add the selected component/command pair to the polling table below the form (shown with
its **Component**, **Command**, and **Kwargs**). Click **Start** at the top to begin polling every variable in the
table at the configured sample time. The same command can be added more than once with different parameters (two
channels of one ADC, for example): each keeps its own readings and profile.

## Start, Stop and the live platform view

**Start** and **Stop** also switch the Dashboard's [live platform view](overview.md#live-view): the diagram is live
while monitoring is on from this page (the header shows **Platform view live**).

* They work during a protocol run too. A run keeps monitoring on for its own duration either way; **Start** then
  makes the diagram live and keeps monitoring on after the run, and **Stop** turns the live view off while the run
  goes on polling until it ends.
* **Start** works with no variables in the table: the diagram goes live, with nothing to read.
* The variable table stays locked while monitoring polls.

## Profiles

The right card shows a live panel per polled variable once a session is running, plotting readings as they come
in. With no variables added yet, it shows **No variables selected**.
