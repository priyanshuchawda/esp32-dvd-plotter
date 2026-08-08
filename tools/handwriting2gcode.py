#!/usr/bin/env python3
"""Generate handwriting with a neural model and emit plotter G-code.

Uses Graves-style LSTM synthesis (X-rayLaser's PyTorch toolkit), which predicts
pen trajectories directly, so no vectorisation step is needed. Run
tools/setup_handwriting.sh first, then invoke through the environment it builds:

    ext/venv/bin/python tools/handwriting2gcode.py "hello world" -o hello.gcode

Raise --bias for cleaner, more legible output; lower it for more natural
variation. At the size a 35 mm bed forces, legibility usually wins.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TOOLKIT = REPO_ROOT / "ext" / "handwriting-synthesis"


def load_toolkit(toolkit_path):
    if not (toolkit_path / "handwriting_synthesis").is_dir():
        sys.exit(f"handwriting toolkit not found at {toolkit_path}.\n"
                 f"Run tools/setup_handwriting.sh first.")
    sys.path.insert(0, str(toolkit_path))
    # The toolkit resolves some resources relative to the working directory.
    os.chdir(toolkit_path)
    try:
        import torch
        from handwriting_synthesis.sampling import HandwritingSynthesizer
        from handwriting_synthesis.utils import split_into_components, get_strokes
    except ImportError as exc:
        sys.exit(f"cannot import the toolkit ({exc}).\n"
                 f"Run through its environment: ext/venv/bin/python {sys.argv[0]} ...")
    return torch, HandwritingSynthesizer, split_into_components, get_strokes


def simplify(points, tolerance):
    """Ramer-Douglas-Peucker, to keep the G-code a sane size."""
    if tolerance <= 0 or len(points) < 3:
        return points
    start, end = points[0], points[-1]
    span = math.dist(start, end)
    worst_index, worst = 0, -1.0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        if span == 0:
            distance = math.dist(points[i], start)
        else:
            distance = abs((end[0] - start[0]) * (start[1] - py)
                           - (start[0] - px) * (end[1] - start[1])) / span
        if distance > worst:
            worst_index, worst = i, distance
    if worst <= tolerance:
        return [start, end]
    left = simplify(points[:worst_index + 1], tolerance)
    right = simplify(points[worst_index:], tolerance)
    return left[:-1] + right


# The model stops as soon as its attention window covers the final character.
# On a short line the window spans the whole string at the first step, so it
# stops before drawing anything. Trailing spaces push the end far enough away;
# 16 characters of context clears it even for a single letter.
MIN_CONTEXT = 16
ATTEMPTS = 6


def sample_line(synthesizer, text, helpers, steps_per_char):
    """Sample one line and return its strokes in model units, y pointing up."""
    torch, _, split_into_components, get_strokes = helpers
    padded = text + " " * max(4, MIN_CONTEXT - len(text))
    context = synthesizer._encode_text(padded)
    steps = max(int(len(padded) * steps_per_char), 60)

    # Sampling is stochastic, so an unlucky draw can still terminate early.
    for _ in range(ATTEMPTS):
        with torch.no_grad():
            sampled = synthesizer.model.sample_means(context=context, steps=steps,
                                                     stochastic=True)
        sampled = synthesizer._undo_normalization(sampled.cpu())
        x, y, eos = split_into_components(sampled)
        # The toolkit draws with y increasing downward; the plotter's Y points up.
        strokes = [[(px, -py) for px, py in stroke]
                   for stroke in get_strokes(x, y, eos) if len(stroke) > 1]
        if strokes:
            return strokes
    return []


def bounds(strokes):
    xs = [p[0] for s in strokes for p in s]
    ys = [p[1] for s in strokes for p in s]
    return min(xs), min(ys), max(xs), max(ys)


def to_gcode(paths, args):
    out = [
        f"; neural handwriting, bias {args.bias:g}",
        "G21", "G90", f"M300 S{args.pen_up_s}", "G0 X0 Y0",
    ]
    drawn = 0.0
    for path in paths:
        out.append(f"G0 X{path[0][0]:.3f} Y{path[0][1]:.3f}")
        out.append(f"M300 S{args.pen_down_s}")
        previous = path[0]
        for point in path[1:]:
            out.append(f"G1 X{point[0]:.3f} Y{point[1]:.3f} F{args.feed:g}")
            drawn += math.dist(previous, point)
            previous = point
        out.append(f"M300 S{args.pen_up_s}")
    out += [f"M300 S{args.pen_up_s}", "G0 X0 Y0", "M18"]
    return "\n".join(out) + "\n", drawn


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("text", nargs="?")
    parser.add_argument("-f", "--file", type=Path)
    parser.add_argument("-o", "--output", default="handwriting.gcode")
    parser.add_argument("-b", "--bias", type=float, default=1.0,
                        help="higher is cleaner and more legible (default 1.0)")
    parser.add_argument("--wrap", type=int, default=12,
                        help="characters per line before wrapping")
    parser.add_argument("--checkpoint", default="Epoch_56")
    parser.add_argument("--toolkit", type=Path, default=DEFAULT_TOOLKIT)
    parser.add_argument("--seed", type=int, help="fix the random style")
    parser.add_argument("--skip-unsupported", action="store_true",
                        help="drop characters the model cannot write instead of "
                             "refusing to run")
    parser.add_argument("--steps-per-char", type=float, default=32.0,
                        help="sampling budget per character")
    parser.add_argument("--width", type=float, default=35.0)
    parser.add_argument("--height", type=float, default=35.0)
    parser.add_argument("--margin", type=float, default=2.0)
    parser.add_argument("--line-spacing", type=float, default=1.35,
                        help="line pitch as a multiple of line height")
    parser.add_argument("--simplify", type=float, default=0.05,
                        help="stroke simplification tolerance in mm")
    parser.add_argument("--min-stroke", type=float, default=0.15,
                        help="drop strokes shorter than this, in mm. The default "
                             "is one motor step, below which nothing can be drawn")
    parser.add_argument("--feed", type=float, default=300.0)
    parser.add_argument("--pen-up-s", type=int, default=50)
    parser.add_argument("--pen-down-s", type=int, default=30)
    args = parser.parse_args()

    if args.file:
        text = args.file.read_text()
    elif args.text:
        text = args.text
    else:
        parser.error("give some text, or --file")

    output = Path(args.output).resolve()
    toolkit = args.toolkit.resolve()
    torch, Synthesizer, split_components, get_strokes = load_toolkit(toolkit)
    helpers = (torch, Synthesizer, split_components, get_strokes)

    if args.seed is not None:
        torch.manual_seed(args.seed)

    checkpoint = toolkit / "checkpoints" / args.checkpoint
    if not checkpoint.is_dir():
        sys.exit(f"no checkpoint at {checkpoint}")

    # Characters outside the alphabet are tokenised to 0 rather than rejected,
    # so the model quietly writes something arbitrary in their place.
    charset = set(json.loads((checkpoint / "meta.json").read_text())["charset"])
    unsupported = sorted(set(text) - charset - {"\n"})
    if unsupported:
        shown = " ".join(repr(c) for c in unsupported)
        if args.skip_unsupported:
            print(f"dropping characters the model cannot write: {shown}",
                  file=sys.stderr)
            text = "".join(c for c in text if c in charset or c == "\n")
        else:
            sys.exit(f"the model has no glyph for: {shown}\n"
                     f"It would write something arbitrary instead, so nothing "
                     f"was generated. Rephrase, or pass --skip-unsupported.")

    rows = [row for block in text.split("\n")
            for row in (textwrap.wrap(block, args.wrap) or [""]) if row]
    if not rows:
        sys.exit("nothing to write")
    synthesizer = Synthesizer.load(str(checkpoint), torch.device("cpu"), args.bias)

    print(f"sampling {len(rows)} line(s) on CPU...", file=sys.stderr)
    sampled = []
    for row in rows:
        strokes = sample_line(synthesizer, row, helpers, args.steps_per_char)
        if not strokes:
            sys.exit(f"the model gave up on {row!r} after {ATTEMPTS} attempts. "
                     f"Dropping it would silently lose text from your page, so "
                     f"nothing was written. Try a different --seed.")
        sampled.append(strokes)
        print(f"  {row!r}: {len(strokes)} strokes", file=sys.stderr)

    # One scale for every line, so letters stay the same size down the page.
    usable_w = args.width - 2 * args.margin
    usable_h = args.height - 2 * args.margin
    boxes = [bounds(s) for s in sampled]
    widest = max(x1 - x0 for x0, _, x1, _ in boxes)
    tallest = max(y1 - y0 for _, y0, _, y1 in boxes)
    if widest <= 0 or tallest <= 0:
        sys.exit("degenerate sample; try rerunning")

    scale = usable_w / widest
    pitch = tallest * scale * args.line_spacing
    if pitch * len(sampled) > usable_h:
        scale *= usable_h / (pitch * len(sampled))
        pitch = tallest * scale * args.line_spacing

    paths = []
    top = args.height - args.margin
    for strokes, (x0, _, _, y1) in zip(sampled, boxes):
        baseline = top - tallest * scale
        for stroke in strokes:
            placed = [(args.margin + (px - x0) * scale,
                       baseline + (py - y1 + tallest) * scale)
                      for px, py in stroke]
            simplified = simplify(placed, args.simplify)
            if len(simplified) < 2:
                continue
            length = sum(math.dist(a, b)
                         for a, b in zip(simplified, simplified[1:]))
            if length >= args.min_stroke:
                paths.append(simplified)
        top -= pitch

    body, drawn = to_gcode(paths, args)
    output.write_text(body)

    points = sum(len(p) for p in paths)
    line_mm = tallest * scale
    print(f"{output}: {len(sampled)} lines, {len(paths)} strokes, {points} points, "
          f"{drawn:.0f} mm drawn, about {drawn / args.feed:.1f} min at F{args.feed:g}")
    print(f"line height {line_mm:.1f} mm")
    if line_mm < 2.5:
        print("warning: lines under about 2.5 mm tall will not be readable at this "
              "machine's 0.15 mm step. Lower --wrap to fit fewer characters per line.",
              file=sys.stderr)


if __name__ == "__main__":
    main()
