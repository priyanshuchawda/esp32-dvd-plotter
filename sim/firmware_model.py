"""Faithful Python port of the motion logic in src/esp32_l293d_plotter.ino.

This mirrors the firmware step-for-step so that simulation reproduces real
behaviour, including integer step rounding and the Bresenham interleave. If the
firmware motion code changes, this file must change with it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

MIN_STEP_INTERVAL_US = 2000
RAPID_FEED_MM_MIN = 300.0
DEFAULT_FEED_MM_MIN = 180.0

# applyPhase(): (coil1A, coil1B, coil2A, coil2B) for phase 0..3.
PHASE_TABLE = (
    (1, 0, 1, 0),
    (0, 1, 1, 0),
    (0, 1, 0, 1),
    (1, 0, 0, 1),
)


def lroundf(value: float) -> int:
    """C lroundf: round half away from zero, unlike Python's banker's rounding."""
    return int(math.floor(value + 0.5)) if value >= 0 else int(math.ceil(value - 0.5))


def to_steps(position_mm: float, steps_per_mm: float) -> int:
    """Mirror lroundf(position * stepsPerMm) evaluated in 32-bit float."""
    return lroundf(float(np.float32(position_mm) * np.float32(steps_per_mm)))


@dataclass
class StepEvent:
    time_us: int
    x_steps: int
    y_steps: int
    x_phase: int
    y_phase: int
    pen_down: bool


@dataclass
class FourWireStepper:
    phase: int = 0
    position_steps: int = 0

    def step(self, direction: int) -> None:
        self.phase = (self.phase + (1 if direction > 0 else 3)) & 0x03

        self.position_steps += 1 if direction > 0 else -1

    @property
    def coils(self) -> tuple[int, int, int, int]:
        return PHASE_TABLE[self.phase & 0x03]


@dataclass
class PlotterModel:
    steps_per_mm_x: float = 6.667
    steps_per_mm_y: float = 6.667

    x_motor: FourWireStepper = field(default_factory=FourWireStepper)
    y_motor: FourWireStepper = field(default_factory=FourWireStepper)

    x_position_mm: float = 0.0
    y_position_mm: float = 0.0
    feed_rate_mm_min: float = DEFAULT_FEED_MM_MIN
    unit_scale_mm: float = 1.0
    absolute_mode: bool = True
    motors_enabled: bool = False
    pen_down: bool = False
    pen_settle_ms: int = 250
    pen_down_threshold_s: float = 40.0

    time_us: int = 0
    events: list[StepEvent] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def _record(self) -> None:
        self.events.append(
            StepEvent(
                time_us=self.time_us,
                x_steps=self.x_motor.position_steps,
                y_steps=self.y_motor.position_steps,
                x_phase=self.x_motor.phase,
                y_phase=self.y_motor.phase,
                pen_down=self.pen_down,
            )
        )

    def set_pen(self, down: bool) -> None:
        if down != self.pen_down:
            self.pen_down = down
            self.time_us += self.pen_settle_ms * 1000
            self._record()

    def move_linear(self, target_x: float, target_y: float, feed_mm_min: float) -> None:
        target_x_steps = to_steps(target_x, self.steps_per_mm_x)
        target_y_steps = to_steps(target_y, self.steps_per_mm_y)
        delta_x = target_x_steps - self.x_motor.position_steps
        delta_y = target_y_steps - self.y_motor.position_steps
        abs_x = abs(delta_x)
        abs_y = abs(delta_y)
        major_steps = max(abs_x, abs_y)

        if major_steps == 0:
            self.x_position_mm = target_x
            self.y_position_mm = target_y
            return

        self.motors_enabled = True
        distance_mm = math.hypot(target_x - self.x_position_mm, target_y - self.y_position_mm)
        safe_feed = max(feed_mm_min, 1.0)
        interval_us = max(
            MIN_STEP_INTERVAL_US,
            int((distance_mm * 60_000_000.0) / (safe_feed * major_steps)),
        )

        error = abs_x - abs_y
        sign_x = 1 if delta_x >= 0 else -1
        sign_y = 1 if delta_y >= 0 else -1

        guard = 4 * (abs_x + abs_y) + 16
        iterations = 0

        while True:
            if (
                self.x_motor.position_steps == target_x_steps
                and self.y_motor.position_steps == target_y_steps
            ):
                break

            iterations += 1
            if iterations > guard:
                self.errors.append(
                    f"Bresenham loop failed to converge toward "
                    f"X{target_x:.3f} Y{target_y:.3f}"
                )
                break

            twice_error = 2 * error
            if twice_error > -abs_y and self.x_motor.position_steps != target_x_steps:
                error -= abs_y
                self.x_motor.step(sign_x)
            if twice_error < abs_x and self.y_motor.position_steps != target_y_steps:
                error += abs_x
                self.y_motor.step(sign_y)

            self.time_us += interval_us
            self._record()

        self.x_position_mm = target_x
        self.y_position_mm = target_y

    def execute(self, raw_line: str) -> None:
        line = raw_line.split(";")[0].strip().upper()
        if not line:
            return

        if line.startswith("$") or line == "?":
            self._execute_system(line)
            return

        g_code = _extract_int(line, "G")
        m_code = _extract_int(line, "M")

        if m_code in (3, 4):
            self.set_pen(True)
            return
        if m_code == 5:
            self.set_pen(False)
            return
        if m_code in (2, 30):
            self.set_pen(False)
            self.motors_enabled = False
            return
        # M300 (Unicorn) and M280 carry the pen angle in S; low means down.
        if m_code in (300, 280):
            s_value = _extract_float(line, "S")
            if s_value is not None:
                self.set_pen(s_value <= self.pen_down_threshold_s)
            return
        if m_code in (18, 84):
            self.motors_enabled = False
            return
        if m_code in (105, 114):
            return

        if g_code == 20:
            self.unit_scale_mm = 25.4
            return
        if g_code == 21:
            self.unit_scale_mm = 1.0
            return
        if g_code == 90:
            self.absolute_mode = True
            return
        if g_code == 91:
            self.absolute_mode = False
            return
        if g_code == 92:
            x = _extract_float(line, "X")
            y = _extract_float(line, "Y")
            if x is not None:
                self.x_position_mm = x * self.unit_scale_mm
            if y is not None:
                self.y_position_mm = y * self.unit_scale_mm
            self.x_motor.position_steps = to_steps(self.x_position_mm, self.steps_per_mm_x)
            self.y_motor.position_steps = to_steps(self.y_position_mm, self.steps_per_mm_y)
            return

        if g_code == 28:
            self.set_pen(False)
            self.move_linear(0.0, 0.0, RAPID_FEED_MM_MIN)
            return

        if g_code not in (0, 1):
            self.errors.append(f"Unsupported command rejected by firmware: {line}")
            return

        x_value = _extract_float(line, "X")
        y_value = _extract_float(line, "Y")
        z_value = _extract_float(line, "Z")
        feed = _extract_float(line, "F")
        if feed is not None:
            self.feed_rate_mm_min = feed * self.unit_scale_mm

        x = x_value * self.unit_scale_mm if x_value is not None else self.x_position_mm
        y = y_value * self.unit_scale_mm if y_value is not None else self.y_position_mm
        if not self.absolute_mode:
            if x_value is not None:
                x += self.x_position_mm
            if y_value is not None:
                y += self.y_position_mm

        if z_value is not None:
            self.set_pen(z_value * self.unit_scale_mm <= 0.0)
        if x_value is not None or y_value is not None:
            self.move_linear(x, y, RAPID_FEED_MM_MIN if g_code == 0 else self.feed_rate_mm_min)

    def _execute_system(self, line: str) -> None:
        for prefix, attribute in (("$STEPSX=", "steps_per_mm_x"), ("$STEPSY=", "steps_per_mm_y")):
            if line.startswith(prefix):
                value = float(line[len(prefix) :])
                if value <= 0:
                    self.errors.append(f"Rejected non-positive setting: {line}")
                else:
                    setattr(self, attribute, value)
                return
        if line == "$MOTORS=ON":
            self.motors_enabled = True
        elif line == "$MOTORS=OFF":
            self.motors_enabled = False

    def run(self, gcode: str) -> "PlotterModel":
        for raw_line in gcode.splitlines():
            self.execute(raw_line)
        return self


def _extract_float(line: str, code: str) -> float | None:
    """Mirror extractValue(): skip a code preceded by another letter."""
    for index, character in enumerate(line):
        if character != code:
            continue
        if index > 0 and line[index - 1].isalpha():
            continue
        remainder = line[index + 1 :]
        parsed = _parse_leading_float(remainder)
        if parsed is not None:
            return parsed
    return None


def _extract_int(line: str, code: str) -> int:
    value = _extract_float(line, code)
    return lroundf(value) if value is not None else -1


def _parse_leading_float(text: str) -> float | None:
    """Emulate strtof(): consume the longest valid numeric prefix."""
    matched = None
    for end in range(len(text), 0, -1):
        candidate = text[:end]
        try:
            matched = float(candidate)
        except ValueError:
            continue
        return matched
    return matched
