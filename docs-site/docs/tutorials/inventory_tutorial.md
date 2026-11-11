# 2. Add a substance and fill the vessel

Continue from [drawing the setup](drawing_tutorial.md). Define ethanol, then give vessel `A` an initial liquid inventory of `10 mL`. Leave vessel `B` empty of liquid.

```{image} ../_static/tutorials/02-substance-and-filling.gif
:alt: Adding ethanol to the compound list and applying a 10 mL liquid inventory to vessel A.
:width: 100%
```

## Add ethanol

Open **Compounds** in the sidebar and click **Add compound**. Enter the following values to match the recording:

| Property | Tutorial value |
| --- | --- |
| Name | `ethanol` |
| Molecular weight | `46.06844 g/mol` |
| Liquid density | `789 kg/m³` |
| Liquid heat capacity | `112.4 J/(mol·K)` |
| Gas heat capacity | `65 J/(mol·K)` |
| Red / Green / Blue / Transparency | `225` / `145` / `45` / `220` |

The orange color makes the liquid easier to follow during simulation. Click **Save** to add the compound.

## Fill vessel A

1. Open **Inventory** in the sidebar. The page is titled **Initial Inventory**.
2. Select `A` in the component table.
3. Under **Liquid**, set **Volume** to `10 mL`.
4. In the liquid **Composition** selector, choose `ethanol` and click **Add compound**.
5. On the ethanol row, select **equiv. mL** as the unit and enter `10` as the amount. Both the liquid volume and the compound amount need to be set.
6. Keep **Auto-fill gas headspace** enabled, then click **Apply changes**.
7. Save the project using **Project → Save Project**.

After applying, A contains `10 mL` of liquid ethanol and B still has `0 mL` of liquid. The editor may display the ethanol amount in moles after applying; it represents the same inventory.

These are the starting contents used by the simulation. See [Compounds & Initial Inventory](../simulation/digital_twins.md#compounds--initial-inventory) for more about phases and composition units.

Previous: [1. Draw the setup](drawing_tutorial.md). Next: [3. Build the protocol](protocols_tutorial.md).
