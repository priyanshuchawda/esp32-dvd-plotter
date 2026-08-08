#!/usr/bin/env python3
"""Render text to pen-plotter G-code using single-stroke Hershey fonts.

Do not route text through image2gcode. Tracing a normal font produces the
*outline* of each letter, so you get hollow shapes drawn twice, which is
unreadable at the few millimetres this machine has to work with. Hershey fonts
store the centreline of each stroke, which is what a pen actually follows.

    tools/text2gcode.py "hello world" -o hello.gcode
    tools/text2gcode.py --font cursive --char-height 3.5 "your text"
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

FONT_DIR = Path(__file__).parent / "fonts"

# Hershey glyphs are stored with y increasing downward, the baseline at +9,
# and capitals reaching up to -12, so a capital spans 21 units.
BASELINE = 9
CAP_HEIGHT = 21
ORIGIN = ord("R")
FIRST_CHAR = 32


def load_font(name):
    path = FONT_DIR / f"{name}.jhf"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in FONT_DIR.glob("*.jhf")))
        sys.exit(f"no font '{name}'. Available: {available}")

    glyphs = {}
    lines = path.read_text().splitlines()
    index = 0
    code = FIRST_CHAR
    while index < len(lines):
        line = lines[index]
        index += 1
        if not line.strip():
            continue
        count = int(line[5:8])
        data = line[8:]
        # Long glyphs can spill onto the following line.
        while len(data) < 2 * count and index < len(lines):
            data += lines[index]
            index += 1

        left = ord(data[0]) - ORIGIN
        right = ord(data[1]) - ORIGIN
        strokes, current = [], []
        for at in range(2, 2 * count, 2):
            pair = data[at:at + 2]
            if len(pair) < 2:
                break
            if pair[0] == " ":          # pen up, start a new stroke
                if len(current) > 1:
                    strokes.append(current)
                current = []
                continue
            current.append((ord(pair[0]) - ORIGIN, ord(pair[1]) - ORIGIN))
        if len(current) > 1:
            strokes.append(current)

        glyphs[chr(code)] = {"left": left, "right": right, "strokes": strokes}
        code += 1
    return glyphs


def advance(glyphs, character, spacing):
    glyph = glyphs.get(character)
    if glyph is None:
        return CAP_HEIGHT * 0.5
    return (glyph["right"] - glyph["left"]) + spacing


def wrap(text, glyphs, spacing, max_units):
    """Greedy word wrap measured in font units, not characters."""
    rows = []
    for paragraph in text.split("\n"):
        row, width = [], 0.0
        for word in paragraph.split():
            word_width = sum(advance(glyphs, c, spacing) for c in word)
            space_width = advance(glyphs, " ", spacing)
            extra = word_width if not row else space_width + word_width
            if row and width + extra > max_units:
                rows.append(" ".join(row))
                row, width = [word], word_width
            else:
                row.append(word)
                width += extra
        rows.append(" ".join(row))
    return rows


def layout(rows, glyphs, args, scale, spacing):
    """Turn wrapped rows into millimetre polylines."""
    line_step = args.char_height * args.line_spacing
    paths = []
    baseline_y = args.height - args.margin - args.char_height
    for row in rows:
        pen_x = args.margin
        for character in row:
            glyph = glyphs.get(character)
            if glyph is None:
                pen_x += advance(glyphs, character, spacing) * scale
                continue
            for stroke in glyph["strokes"]:
                paths.append([
                    (pen_x + (gx - glyph["left"]) * scale,
                     baseline_y + (BASELINE - gy) * scale)
                    for gx, gy in stroke
                ])
            pen_x += advance(glyphs, character, spacing) * scale
        baseline_y -= line_step
    return paths, baseline_y + line_step


def to_gcode(paths, args):
    out = [
        f"; text, font {args.font}, {args.char_height:g} mm characters",
        "G21", "G90", f"M300 S{args.pen_up_s}", "G0 X0 Y0",
    ]
    drawn = 0.0
    for path in paths:
        x, y = path[0]
        out.append(f"G0 X{x:.3f} Y{y:.3f}")
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
    parser.add_argument("text", nargs="?", help="text to write")
    parser.add_argument("-f", "--file", type=Path, help="read text from a file")
    parser.add_argument("-o", "--output", default="text.gcode")
    parser.add_argument("--font", default="futural",
                        help="futural (plain), cursive (handwriting-like), timesr, "
                             "futuram, gothiceng")
    parser.add_argument("--char-height", type=float, default=4.0,
                        help="capital letter height in mm")
    parser.add_argument("--line-spacing", type=float, default=1.7,
                        help="line pitch as a multiple of character height")
    parser.add_argument("--letter-spacing", type=float, default=1.0,
                        help="extra gap between letters, in font units")
    parser.add_argument("--width", type=float, default=35.0)
    parser.add_argument("--height", type=float, default=35.0)
    parser.add_argument("--margin", type=float, default=2.0)
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

    glyphs = load_font(args.font)
    scale = args.char_height / CAP_HEIGHT
    usable = args.width - 2 * args.margin
    if usable <= 0:
        sys.exit("margin leaves no room to write")

    rows = wrap(text, glyphs, args.letter_spacing, usable / scale)
    paths, last_baseline = layout(rows, glyphs, args, scale, args.letter_spacing)
    if not paths:
        sys.exit("nothing to draw")

    body, drawn = to_gcode(paths, args)
    Path(args.output).write_text(body)

    points = sum(len(p) for p in paths)
    print(f"{args.output}: {len(rows)} lines, {len(paths)} strokes, {points} points, "
          f"{drawn:.0f} mm drawn, about {drawn / args.feed:.1f} min at F{args.feed:g}")

    if last_baseline < args.margin:
        overflow = args.margin - last_baseline
        print(f"warning: text runs {overflow:.1f} mm past the bottom of the bed. "
              f"Reduce --char-height, or shorten the text.", file=sys.stderr)


if __name__ == "__main__":
    main()
