# Mechanical CAD

[`plotter.scad`](plotter.scad) is a parametric model of the whole machine,
driven from the terminal with OpenSCAD.

Bed defaults match this build’s measurements (**55 × 50 mm**). Other sled
dimensions are still estimates — measure your chassis before cutting or
printing.

## Render and export

```bash
mkdir -p cad/out

# Whole machine (PNG)
openscad -D 'part="assembly"' --imgsize=1200,900 \
  --camera=120,110,70,55,0,30,480 \
  -o cad/out/assembly.png cad/plotter.scad

# Printable parts
openscad -D 'part="pen_lift"' -o cad/out/pen_lift.stl cad/plotter.scad
openscad -D 'part="paper_bed"' -o cad/out/paper_bed.stl cad/plotter.scad
openscad -D 'part="gantry_upright"' -o cad/out/gantry_upright.stl cad/plotter.scad
```

Valid `part` values: `assembly`, `pen_lift`, `paper_bed`, `gantry_upright`.

Confirm manifold solids after edits:

```bash
openscad -D 'part="pen_lift"' -o /tmp/check.stl cad/plotter.scad 2>&1 | grep Simple
```

`Simple: yes` means a valid printable solid.

## Layout

Y sled moves the paper front/back; X sled is overhead and moves the pen
left/right. Usable drawing area is the paper bed: **55 × 50 mm** on this frame
(`sled_travel_x` / `sled_travel_y` / `bed_x` / `bed_y` in the SCAD file).

## Pen bracket

Bolts to the X carriage and hangs down. Guide tube, SG90 cradle, and screw
strip are stacked so they do not overlap. A rubber band can provide pen
down-force; the servo horn lifts the collar.
