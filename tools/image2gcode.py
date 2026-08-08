#!/usr/bin/env python3
"""Turn an image into pen-plotter G-code.

This replaces the Inkscape 0.48 plus MakerBot Unicorn route from the usual
CD-ROM plotter tutorials. That combination is from 2011, is 32-bit Windows
only, and cannot be installed on a current Linux system. Inkscape's "Trace
Bitmap" is really potrace under the hood, so we call potrace directly and skip
the GUI entirely.

    image -> threshold -> potrace -> polygons -> fit to bed -> G-code

The output uses M300 for the pen, which is what the firmware and virtually
every plotter host expect.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

try:
    from shapely.geometry import LineString
except ImportError:
    LineString = None


def trace(image_path, threshold, invert, turdsize, alphamax, max_pixels):
    """Threshold the image and hand it to potrace, returning pixel-space rings."""
    if shutil.which("potrace") is None:
        sys.exit("potrace not found. Install it with: sudo dnf install potrace")

    img = Image.open(image_path)
    # Flatten transparency onto white, or RGBA images come out solid black.
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(canvas, img)
    img = img.convert("L")

    # Tracing a huge photo produces tens of thousands of segments that plot for
    # hours, so cap the working resolution.
    if max(img.size) > max_pixels:
        scale = max_pixels / max(img.size)
        img = img.resize(
            (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
            Image.LANCZOS,
        )

    if invert:
        img = ImageOps.invert(img)
    # potrace traces black regions, so anything darker than the threshold is ink.
    bitmap = img.point(lambda p: 0 if p < threshold else 255, mode="1")

    with tempfile.TemporaryDirectory() as tmp:
        pbm = Path(tmp) / "in.pbm"
        out = Path(tmp) / "out.json"
        bitmap.save(pbm)
        subprocess.run(
            ["potrace", "-b", "geojson", "-a", str(alphamax),
             "-t", str(turdsize), "-o", str(out), str(pbm)],
            check=True,
        )
        data = json.loads(out.read_text())

    rings = []
    for feature in data.get("features", []):
        geometry = feature.get("geometry") or {}
        kind = geometry.get("type")
        if kind == "Polygon":
            polygons = [geometry["coordinates"]]
        elif kind == "MultiPolygon":
            polygons = geometry["coordinates"]
        else:
            continue
        for polygon in polygons:
            for ring in polygon:
                if len(ring) >= 2:
                    rings.append([(float(x), float(y)) for x, y in ring])
    return rings


def simplify(rings, tolerance):
    """Drop redundant points. Fewer points means less serial traffic mid-plot."""
    if tolerance <= 0 or LineString is None:
        return rings
    out = []
    for ring in rings:
        simplified = LineString(ring).simplify(tolerance, preserve_topology=False)
        coords = list(simplified.coords)
        out.append(coords if len(coords) >= 2 else ring)
    return out


def order_for_travel(rings):
    """Greedy nearest-neighbour ordering, which cuts pen-up travel a lot."""
    if not rings:
        return []
    remaining = list(rings)
    ordered = [remaining.pop(0)]
    while remaining:
        cx, cy = ordered[-1][-1]
        best = min(
            range(len(remaining)),
            key=lambda i: (remaining[i][0][0] - cx) ** 2 + (remaining[i][0][1] - cy) ** 2,
        )
        ordered.append(remaining.pop(best))
    return ordered


def fit(rings, width, height, margin):
    """Scale and centre the drawing inside the bed, preserving aspect ratio."""
    points = [p for ring in rings for p in ring]
    min_x = min(p[0] for p in points)
    max_x = max(p[0] for p in points)
    min_y = min(p[1] for p in points)
    max_y = max(p[1] for p in points)
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)

    usable_w = width - 2 * margin
    usable_h = height - 2 * margin
    if usable_w <= 0 or usable_h <= 0:
        sys.exit("margin is larger than the bed; nothing left to draw on")

    scale = min(usable_w / span_x, usable_h / span_y)
    offset_x = (width - span_x * scale) / 2
    offset_y = (height - span_y * scale) / 2

    return [
        [((x - min_x) * scale + offset_x, (y - min_y) * scale + offset_y) for x, y in ring]
        for ring in rings
    ], scale


def to_gcode(rings, args):
    lines = [
        f"; {len(rings)} paths, bed {args.width:g} x {args.height:g} mm",
        "; pen: M300 S{} down, S{} up".format(args.pen_down_s, args.pen_up_s),
        "G21",
        "G90",
        f"M300 S{args.pen_up_s}",
        "G0 X0 Y0",
    ]
    total_draw = 0.0
    for ring in rings:
        start_x, start_y = ring[0]
        lines.append(f"G0 X{start_x:.3f} Y{start_y:.3f}")
        lines.append(f"M300 S{args.pen_down_s}")
        previous = ring[0]
        for x, y in ring[1:]:
            lines.append(f"G1 X{x:.3f} Y{y:.3f} F{args.feed:g}")
            total_draw += math.dist(previous, (x, y))
            previous = (x, y)
        lines.append(f"M300 S{args.pen_up_s}")
    lines += [f"M300 S{args.pen_up_s}", "G0 X0 Y0", "M18"]
    return "\n".join(lines) + "\n", total_draw


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image", help="input PNG, JPG, or similar")
    parser.add_argument("-o", "--output", default="out.gcode")
    parser.add_argument("--width", type=float, default=35.0,
                        help="usable bed width in mm (default 35)")
    parser.add_argument("--height", type=float, default=35.0)
    parser.add_argument("--margin", type=float, default=2.0)
    parser.add_argument("--feed", type=float, default=300.0,
                        help="drawing feed rate in mm/min")
    parser.add_argument("--threshold", type=int, default=128,
                        help="0-255; higher captures more of the image as ink")
    parser.add_argument("--invert", action="store_true",
                        help="use for light drawings on a dark background")
    parser.add_argument("--turdsize", type=int, default=4,
                        help="discard specks smaller than this many pixels")
    parser.add_argument("--alphamax", type=float, default=1.0,
                        help="potrace corner smoothing; 0 gives straight polygons")
    parser.add_argument("--simplify", type=float, default=0.4,
                        help="point-reduction tolerance in source pixels")
    parser.add_argument("--max-pixels", type=int, default=600,
                        help="downscale the long edge to this before tracing")
    parser.add_argument("--pen-up-s", type=int, default=50)
    parser.add_argument("--pen-down-s", type=int, default=30)
    args = parser.parse_args()

    rings = trace(args.image, args.threshold, args.invert,
                  args.turdsize, args.alphamax, args.max_pixels)
    if not rings:
        sys.exit("nothing was traced. Try adjusting --threshold, or --invert.")

    rings = simplify(rings, args.simplify)
    rings = order_for_travel(rings)
    rings, scale = fit(rings, args.width, args.height, args.margin)
    text, draw_mm = to_gcode(rings, args)
    Path(args.output).write_text(text)

    points = sum(len(r) for r in rings)
    minutes = draw_mm / args.feed if args.feed else 0
    print(f"{args.output}: {len(rings)} paths, {points} points, "
          f"{draw_mm:.0f} mm of drawing, about {minutes:.1f} min at F{args.feed:g}")
    if points > 4000:
        print("warning: that is a lot of points. Raise --simplify or lower "
              "--max-pixels if the plot takes too long.")


if __name__ == "__main__":
    main()
