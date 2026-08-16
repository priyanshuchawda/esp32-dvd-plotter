#!/usr/bin/env python3
"""Simulate a G-code job against the plotter firmware model and render the result.

Usage:
  python3 sim/simulate.py test-square-uno.gcode
  python3 sim/simulate.py hi.gcode --width 55 --height 50 --steps-x 2.058 --steps-y 2.058
  python3 sim/simulate.py hi.gcode --paper   # ink-only page preview (no coils)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from firmware_model import PHASE_TABLE, PlotterModel  # noqa: E402

SIGNAL_LABELS = (
    "X M1A", "X M1B", "X M2A", "X M2B",
    "Y M3A", "Y M3B", "Y M4A", "Y M4B",
)

# Defaults match the measured Uno + HW-130 frame (see FINDINGS.md).
DEFAULT_WIDTH = 55.0
DEFAULT_HEIGHT = 50.0
DEFAULT_STEPS = 2.058


def build_segments(model: PlotterModel):
    """Group consecutive step events into pen-down and pen-up polylines."""
    segments: list[tuple[bool, list[tuple[float, float]]]] = []
    current_pen = None
    points: list[tuple[float, float]] = []

    previous = (0.0, 0.0)
    for event in model.events:
        position = (
            event.x_steps / model.steps_per_mm_x,
            event.y_steps / model.steps_per_mm_y,
        )
        if event.pen_down != current_pen:
            if points:
                segments.append((bool(current_pen), points))
            current_pen = event.pen_down
            points = [previous]
        points.append(position)
        previous = position

    if points:
        segments.append((bool(current_pen), points))
    return segments


def _draw_paths(path_axes, segments, width_mm: float, height_mm: float,
                paper: bool) -> None:
    if paper:
        path_axes.set_facecolor("#f4f1ea")
        path_axes.add_patch(
            Rectangle((0, 0), width_mm, height_mm, fill=True,
                      facecolor="#fffdf8", edgecolor="#333333", linewidth=1.2)
        )
        for pen_down, points in segments:
            if not pen_down:
                continue
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            path_axes.plot(xs, ys, linewidth=1.8, color="#1a1a1a",
                           solid_capstyle="round", solid_joinstyle="round", zorder=3)
        path_axes.set_title("Paper preview (ink only)")
    else:
        for pen_down, points in segments:
            xs = [p[0] for p in points]
            ys = [p[1] for p in points]
            if pen_down:
                path_axes.plot(xs, ys, linewidth=2.0, color="#1f4fd8", zorder=3)
            else:
                path_axes.plot(xs, ys, linewidth=1.0, color="#c23b22",
                               linestyle="--", alpha=0.75, zorder=2)
        path_axes.add_patch(
            Rectangle((0, 0), width_mm, height_mm, fill=False,
                      edgecolor="#888888", linestyle=":", linewidth=1.2)
        )
        path_axes.plot([], [], color="#1f4fd8", linewidth=2.0, label="pen down (drawn)")
        path_axes.plot([], [], color="#c23b22", linestyle="--", label="pen up (travel)")
        path_axes.plot([], [], color="#888888", linestyle=":",
                       label=f"bed {width_mm:g}×{height_mm:g} mm")
        path_axes.legend(loc="upper right", fontsize=8)
        path_axes.set_title("Toolpath")

    path_axes.set_aspect("equal", adjustable="box")
    path_axes.set_xlim(-2, width_mm + 2)
    path_axes.set_ylim(-2, height_mm + 2)
    path_axes.grid(True, alpha=0.25)
    path_axes.set_xlabel("X (mm)")
    path_axes.set_ylabel("Y (mm)")


def render(model: PlotterModel, segments, width_mm: float, height_mm: float,
           output: Path, title: str, paper: bool) -> None:
    if paper:
        figure = plt.figure(figsize=(6.5, 6.0))
        path_axes = figure.add_subplot(1, 1, 1)
        _draw_paths(path_axes, segments, width_mm, height_mm, paper=True)
        path_axes.set_title(f"{title} — paper preview")
    else:
        figure = plt.figure(figsize=(13, 6))
        path_axes = figure.add_subplot(1, 2, 1)
        coil_axes = figure.add_subplot(1, 2, 2)
        _draw_paths(path_axes, segments, width_mm, height_mm, paper=False)
        path_axes.set_title(f"Toolpath: {title}")
        _render_coils(model, coil_axes)

    figure.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=120)
    plt.close(figure)


def _render_coils(model: PlotterModel, axes, max_events: int = 40) -> None:
    events = [event for event in model.events if event.time_us > 0][:max_events]
    if not events:
        axes.text(0.5, 0.5, "no step events", ha="center", va="center")
        axes.set_axis_off()
        return

    times = [event.time_us / 1000.0 for event in events]
    for index, label in enumerate(SIGNAL_LABELS):
        offset = (len(SIGNAL_LABELS) - 1 - index) * 1.5
        values = []
        for event in events:
            phase = event.x_phase if index < 4 else event.y_phase
            values.append(PHASE_TABLE[phase][index % 4])
        axes.step(times, [value + offset for value in values], where="post", linewidth=1.4)
        axes.text(times[0], offset + 0.35, label, fontsize=8, va="bottom")

    axes.set_yticks([])
    axes.set_xlabel("simulated time (ms)")
    axes.set_title(f"Coil signals, first {len(events)} steps")
    axes.grid(True, axis="x", alpha=0.3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gcode", type=Path)
    parser.add_argument("--width", type=float, default=DEFAULT_WIDTH,
                        help=f"bed width in mm (default {DEFAULT_WIDTH:g})")
    parser.add_argument("--height", type=float, default=DEFAULT_HEIGHT,
                        help=f"bed height in mm (default {DEFAULT_HEIGHT:g})")
    parser.add_argument("--envelope", type=float, default=None,
                        help="legacy: square bed size; sets both width and height")
    parser.add_argument("--steps-x", type=float, default=DEFAULT_STEPS)
    parser.add_argument("--steps-y", type=float, default=DEFAULT_STEPS)
    parser.add_argument("--paper", action="store_true",
                        help="ink-only page preview (closest stand-in for no pen/paper)")
    parser.add_argument("--out", type=Path, default=None)
    arguments = parser.parse_args()

    width = arguments.width
    height = arguments.height
    if arguments.envelope is not None:
        width = height = arguments.envelope

    gcode = arguments.gcode.read_text()
    model = PlotterModel(
        steps_per_mm_x=arguments.steps_x,
        steps_per_mm_y=arguments.steps_y,
    ).run(gcode)

    segments = build_segments(model)
    suffix = "_paper" if arguments.paper else ""
    output = arguments.out or Path("sim/out") / f"{arguments.gcode.stem}{suffix}.png"
    render(model, segments, width, height, output, arguments.gcode.name, arguments.paper)

    drawn = [points for pen_down, points in segments if pen_down]
    all_points = [point for _, points in segments for point in points]
    xs = [point[0] for point in all_points]
    ys = [point[1] for point in all_points]

    x_steps = sum(
        1 for a, b in zip(model.events, model.events[1:]) if a.x_steps != b.x_steps
    )
    y_steps = sum(
        1 for a, b in zip(model.events, model.events[1:]) if a.y_steps != b.y_steps
    )

    print(f"job              : {arguments.gcode}")
    print(f"bed              : {width:g} x {height:g} mm")
    print(f"resolution       : {1 / model.steps_per_mm_x:.3f} mm per X step, "
          f"{1 / model.steps_per_mm_y:.3f} mm per Y step")
    print(f"step events      : {len(model.events)} ({x_steps} X, {y_steps} Y)")
    print(f"drawn polylines  : {len(drawn)}")
    if xs:
        print(f"extent X         : {min(xs):.2f} .. {max(xs):.2f} mm")
        print(f"extent Y         : {min(ys):.2f} .. {max(ys):.2f} mm")
    print(f"simulated runtime: {model.time_us / 1_000_000:.2f} s")
    print(f"final position   : X{model.x_position_mm:.3f} Y{model.y_position_mm:.3f} "
          f"(pen {'down' if model.pen_down else 'up'}, "
          f"motors {'on' if model.motors_enabled else 'off'})")
    print(f"render           : {output}")

    warnings = list(model.errors)
    if xs and (min(xs) < -1e-6 or max(xs) > width + 1e-6):
        warnings.append(
            f"X travel {min(xs):.2f}..{max(xs):.2f} mm leaves the 0..{width:g} mm bed"
        )
    if ys and (min(ys) < -1e-6 or max(ys) > height + 1e-6):
        warnings.append(
            f"Y travel {min(ys):.2f}..{max(ys):.2f} mm leaves the 0..{height:g} mm bed"
        )
    if model.pen_down:
        warnings.append("job ended with the pen still down")

    if warnings:
        print("\nwarnings:")
        for warning in warnings:
            print(f"  - {warning}")
        return 1

    print("\nno warnings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
