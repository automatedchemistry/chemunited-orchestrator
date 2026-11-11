# 5. Connect the devices

Continue from [4. Simulation](simulation_tutorial.md) with the project saved. Associate the
drawn pump **P01** and **valve** with their online services so the process can send commands
to them.

```{image} ../_static/tutorials/05-connect-devices.gif
:alt: Discovering the tutorial pump and valve, dragging their online services onto P01 and valve, and saving the device associations.
:width: 100%
```

The recording uses temporary local demonstration devices named `tutorial/P01` and
`tutorial/valve`. Their server runs only during the recording; the address shown in the
GIF is not a server you can reuse. For hardware, first start your own FlowChem server
following [Setup Connectivity](../connectivity/connectivity.md), then use its address
and the services it exposes.

## Discover the online services

1. Open **Connectivity**, then **Online List**. Use **Home** to center the drawing if needed.
2. Under **Available Flowchem servers**, select your running server, or enter its URL and
   press **Enter**.
3. Wait for **Available Online Components** to populate. In the recording, it contains
   `tutorial/valve` and `tutorial/P01`.

## Associate and save

1. Drag `tutorial/valve` from the online list onto the drawn **valve**, then release it.
2. Drag `tutorial/P01` onto the drawn syringe pump **P01**.
3. Check the connected indicators on the drawing. Both services should also appear under
   **Lock Online Components**.
4. Save the project through **Project → Save Project**.

The saved associations link the drawing's component names to the online service URLs in
`connectivity/associations.json`. FlowChem associations are managed by the drag-and-drop
interface; see [Associate components](../connectivity/connectivity.md#associate-components)
for details.

Previous: [4. Simulation](simulation_tutorial.md) · Next: [6. Run the dashboard](monitoring_tutorial.md)
