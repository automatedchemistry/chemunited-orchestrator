# 4. Simulate the process

Continue from [3. Build the protocol](protocols_tutorial.md), with **Process** configured and saved. Simulate the valve and pump commands, then use the recorded timeline to inspect how ethanol moves through the setup.

```{image} ../_static/tutorials/04-simulation.gif
:alt: Right-clicking the Process workflow to select Simulate Process, then dragging the report timeline through recorded fluid states with vessel B's Content profile visible.
:width: 100%
```

## Open the simulation report

On the **Protocol** page, open **Process**. Right-click an empty area of its workflow canvas to display the context menu, then choose **Simulate Process**.

The Simulation Report window opens and runs the saved process. Wait for the run to finish and for the timeline slider to appear above the profile tabs.

## Inspect the recorded fluid movement

Click vessel **B** in the report's platform view, then select the **Content** tab. The profile shows B's recorded contents, with a time marker that follows the slider.

Drag the timeline to its left end to return to the initial state. Move it progressively to about **20%, 40%, 60%, 80%**, and finally the right end, pausing at each position to inspect the drawing and profile.

Watch the orange ethanol enter the route from A through the valve and partly fill the **3.14 mL Loop** during withdrawal. Infusion reverses the flow through the loop toward B after the valve changes position. The **Content** profile and its time marker show B's liquid inventory rising as ethanol arrives.

The time label identifies the selected recorded instant and the last available instant. The slider moves through saved snapshots, so its final timestamp can precede the exact end of the process.

The **0.5 mL** setting describes each pump stroke. The liquid reaching B also depends on the initial contents and internal volumes of the tubing and Loop; it is not necessarily 0.5 mL of ethanol.

The report uses its own copy of the setup. Exploring its timeline preserves the saved drawing and initial inventory. See [Digital twins and simulation profiles](../simulation/digital_twins.md) for the other profile tabs and recording behavior.

## Export the playback

Once the recording is available, choose **Export animation…** in the Simulation Report's navigation rail. Select **MP4** or **GIF**, a resolution, and a playback speed, then choose where to save the file. The estimated duration includes a one-second hold on the final recorded state. Recorded results from a process that stopped early can also be exported.

The animation includes the complete platform and the timestamp of the displayed snapshot, including recorded fluid contents, vessel levels, and valve positions. It uses the report's drawing, independently of its current zoom, and leaves the design canvas untouched. The report returns to your selected snapshot after export or cancellation.

Export uses the full recording at 20 frames per second. Each state remains visible until the next recorded instant; there is no interpolation. The default recording interval is two simulation seconds, so a higher video frame rate would not add fluid-motion detail. Increasing playback speed shortens the video and can skip intermediate snapshots. GIF files loop continuously; MP4 files are suitable for ordinary video playback. FFmpeg is supplied with the application, so no separate installation is needed.

You can cancel while frames are rendered or encoded. An existing destination file is replaced only after export succeeds.

[← Previous: Build the protocol](protocols_tutorial.md) · [Next: Connect the devices →](connectivity_tutorial.md)
