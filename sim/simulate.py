#!/usr/bin/env python3
"""Simulate a G-code job against the plotter firmware model and render the result.

Usage:
  python3 sim/simulate.py test-square.gcode
  python3 sim/simulate.py test-square.gcode --envelope 35 --out sim/out/square.png
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from firmware_model import PHASE_TABLE, PlotterModel  # noqa: E402

SIGNAL_LABELS = (
    "X M1A", "X M1B", "X M2A", "X M2B",
    "Y M3A", "Y M3B", "Y M4A", "Y M4B",
)


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


def render(model: PlotterModel, segments, envelope_mm: float, output: Path, title: str) -> None:
    figure = plt.figure(figsize=(13, 6))
    path_axes = figure.add_subplot(1, 2, 1)
    coil_axes = figure.add_subplot(1, 2, 2)

    for pen_down, points in segments:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        if pen_down:
            path_axes.plot(xs, ys, linewidth=2.0, color="#1f4fd8", zorder=3)
        else:
            path_axes.plot(xs, ys, linewidth=1.0, color="#c23b22",
                           linestyle="--", alpha=0.75, zorder=2)

    path_axes.add_patch(
        plt.Rectangle((0, 0), envelope_mm, envelope_mm, fill=False,
                      edgecolor="#888888", linestyle=":", linewidth=1.2)
    )
    path_axes.plot([], [], color="#1f4fd8", linewidth=2.0, label="pen down (drawn)")
    path_axes.plot([], [], color="#c23b22", linestyle="--", label="pen up (travel)")
    path_axes.plot([], [], color="#888888", linestyle=":", label=f"{envelope_mm:g} mm envelope")

    path_axes.set_aspect("equal", adjustable="datalim")
    path_axes.grid(True, alpha=0.3)
    path_axes.set_xlabel("X (mm)")
    path_axes.set_ylabel("Y (mm)")
    path_axes.set_title(f"Toolpath: {title}")
    path_axes.legend(loc="upper right", fontsize=8)

    _render_coils(model, coil_axes)

    figure.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=110)
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gcode", type=Path)
    parser.add_argument("--envelope", type=float, default=35.0,
                        help="assumed usable travel per axis in mm")
    parser.add_argument("--steps-x", type=float, default=6.667)
    parser.add_argument("--steps-y", type=float, default=6.667)
    parser.add_argument("--out", type=Path, default=None)
    arguments = parser.parse_args()

    gcode = arguments.gcode.read_text()
    model = PlotterModel(
        steps_per_mm_x=arguments.steps_x,
        steps_per_mm_y=arguments.steps_y,
    ).run(gcode)

    segments = build_segments(model)
    output = arguments.out or Path("sim/out") / f"{arguments.gcode.stem}.png"
    render(model, segments, arguments.envelope, output, arguments.gcode.name)

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
    if xs and (min(xs) < -1e-6 or max(xs) > arguments.envelope):
        warnings.append(
            f"X travel {min(xs):.2f}..{max(xs):.2f} mm leaves the "
            f"0..{arguments.envelope:g} mm envelope"
        )
    if ys and (min(ys) < -1e-6 or max(ys) > arguments.envelope):
        warnings.append(
            f"Y travel {min(ys):.2f}..{max(ys):.2f} mm leaves the "
            f"0..{arguments.envelope:g} mm envelope"
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
