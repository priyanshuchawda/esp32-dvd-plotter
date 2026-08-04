# Mechanical CAD

[`plotter.scad`](plotter.scad) is a parametric model of the whole machine,
driven entirely from the terminal with OpenSCAD.

**Every dimension is an estimate.** Measure your own salvaged sleds and edit
the values at the top of the file before cutting or printing anything. The
frame heights are derived, not hardcoded, so changing `sled_height` or
`pen_tube_height` moves the gantry to match automatically.

## Render and export

```bash
# Look at the whole machine
openscad -D 'part="assembly"' --imgsize=1100,850 \
  --camera=105,100,60,60,0,25,440 -o cad/out/assembly.png cad/plotter.scad

# Export a printable part
openscad -D 'part="pen_lift"' -o cad/out/pen_lift.stl cad/plotter.scad
```

Valid `part` values: `assembly`, `pen_lift`, `paper_bed`, `gantry_upright`.

## Layout

The two axes must be perpendicular. The Y sled lies flat and moves the paper
front to back; the X sled sits overhead on two uprights and moves the pen left
to right. The uprights stand under the ends of the X rail and are spaced wide
enough to clear the full width of the Y sled between them.

Usable drawing area is `sled_travel` squared, about 38 mm by 38 mm with the
default numbers. That is why the simulator defaults to a 35 mm envelope.

## Pen bracket

The bracket bolts to the top of the X carriage and hangs down. It stacks three
zones that must never overlap:

| Zone | Height | Purpose |
| --- | --- | --- |
| guide tube | `0` to `pen_tube_height` | pen slides vertically, bore open both ends |
| servo cradle | `cradle_z` upward | SG90 drops in, horn faces the pen collar |
| screw strip | top `pen_mount_zone` | clear area for the carriage screws |

A rubber band from the anchor post to a collar on the pen supplies down-force;
the servo horn pushes that collar up to lift the pen.

## Checking your edits

Always confirm a part is still printable after changing parameters:

```bash
openscad -D 'part="pen_lift"' -o /tmp/check.stl cad/plotter.scad 2>&1 | grep Simple
```

`Simple: yes` means a valid 2-manifold solid that will slice. `Simple: no`
means it will not, and the usual cause is two features that merely touch
instead of overlapping. The guide tube originally sat exactly against the
back plate, making it tangent rather than merged; it is now sunk half a wall
into the plate for that reason.
