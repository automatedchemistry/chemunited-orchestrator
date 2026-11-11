# 1. Draw the setup

Build a small liquid-transfer setup, then follow it through simulation and dashboard execution. This walkthrough has six steps. Drawing has separate GIFs for placing components and building connections; each remaining step has its own GIF.

1. [Draw the setup](drawing_tutorial.md).
2. [Add a substance and fill the vessel](inventory_tutorial.md).
3. [Build the protocol](protocols_tutorial.md).
4. [Simulate the process](simulation_tutorial.md).
5. [Connect the devices](connectivity_tutorial.md).
6. [Run the dashboard](monitoring_tutorial.md).

Start with a [new project](../wellcome/new_project.md) and open **Draw** in the desktop app.

## Add the components

```{image} ../_static/tutorials/01-components.gif
:alt: Dragging five components onto the canvas and editing their names, capacities and dimensions.
:width: 100%
```

Drag each component from the library onto the canvas. In its properties dialog, enter the name and values below, then click **Save**. Keep these names throughout the tutorial; the commands refer to them.

| Component | Name | Properties used in the recording |
| --- | --- | --- |
| Glass bottle | `A` | Capacity: `20 mL` |
| Glass bottle | `B` | Capacity: `20 mL` |
| Sixteen-port distribution valve | `valve` | Default properties |
| Loop | `Loop` | Length: `1000 mm`; internal diameter: `2 mm` (about `3.14 mL`) |
| Syringe pump | `P01` | Syringe volume: `1 mL` |

Place B above the left side of the valve and A above the right side, with the loop to the left and the pump below it. This keeps the tubing close to ports 16 and 4 without crossing the valve face.

The loop holds about **3.14 mL**, exceeding the required 3 mL minimum. The short tubing connections below use their own dimensions.

## Connect and route the tubing

```{image} ../_static/tutorials/01-connections.gif
:alt: Connecting flow ports, opening the tubing right-click menu, and dragging inflection points to shape the routes.
:width: 100%
```

Drag from one flow port to the other to create each connection:

| From | Port | To | Port |
| --- | --- | --- | --- |
| `A` | 1 | `valve` | 4 |
| `B` | 1 | `valve` | 16 |
| `valve` | 0 | `Loop` | 2 |
| `Loop` | 1 | `P01` | 1 |

For each connection, right-click the tubing and choose **Add Inflection Point**. Drag the new handle to route the tubing around the components. Then right-click the tubing again, open **Properties**, set its length to `10 mm` and diameter to `0.5 mm`, and click **Save**.

Save the drawing. You should now have five components and four connections. See [Drawing](../drawing/drawing.md) for the other canvas and connection tools.

Next: [2. Add a substance and fill the vessel](inventory_tutorial.md).
