#!/usr/bin/env python3
"""Stream G-code to the plotter over USB serial.

Replaces Pronterface. The firmware answers every line with exactly one "ok",
so this waits for that acknowledgement before sending the next line rather
than blindly dumping the file at the board.

    tools/send_gcode.py drawing.gcode
    tools/send_gcode.py --console          # interactive, for calibration

Interrupting with Ctrl-C lifts the pen and de-energises the motors before
exiting. Killing a plot without that leaves the pen parked on the paper
bleeding ink, and leaves coils energised and heating with no airflow.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

try:
    import serial
except ImportError:
    sys.exit("pyserial missing. Install with: pip install --user pyserial")

SAFE_SHUTDOWN = ["M300 S50", "M18"]


class Plotter:
    def __init__(self, port, baud, timeout):
        self.timeout = timeout
        self.port = serial.Serial(port, baud, timeout=1)
        self.log = []

    def wait_for_boot(self, seconds=3.0):
        """Opening the port toggles DTR and resets the ESP32, so let it boot."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            line = self.port.readline().decode("utf-8", "replace").strip()
            if line:
                print(f"  {line}")
                if "ready" in line.lower():
                    break
        self.port.reset_input_buffer()

    def send(self, command):
        """Send one line and block until the firmware acknowledges it."""
        command = command.strip()
        if not command:
            return True
        self.port.write((command + "\n").encode())
        self.port.flush()

        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            raw = self.port.readline().decode("utf-8", "replace").strip()
            if not raw:
                continue
            if raw.startswith("ok"):
                return True
            # echo: and error: lines are informational; the ok still follows.
            print(f"  < {raw}")
            self.log.append(raw)
        print(f"  ! timed out waiting for ok after: {command}", file=sys.stderr)
        return False

    def shutdown(self):
        for command in SAFE_SHUTDOWN:
            try:
                self.send(command)
            except Exception:
                pass

    def close(self):
        self.port.close()


def stream(plotter, lines, feed_override):
    total = len(lines)
    started = time.monotonic()
    for index, line in enumerate(lines, 1):
        text = line.split(";")[0].strip()
        if not text:
            continue
        if feed_override and text.startswith(("G1", "G01")) and "F" in text:
            head = text.split("F")[0].strip()
            text = f"{head} F{feed_override:g}"
        if not plotter.send(text):
            print("aborting: the board stopped acknowledging", file=sys.stderr)
            return False
        if index % 10 == 0 or index == total:
            elapsed = time.monotonic() - started
            rate = index / elapsed if elapsed else 0
            remaining = (total - index) / rate if rate else 0
            print(
                f"\r  {index}/{total} lines  {100 * index / total:5.1f}%  "
                f"elapsed {elapsed:5.0f}s  eta {remaining:5.0f}s",
                end="",
                flush=True,
            )
    print()
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("gcode", nargs="?", type=Path)
    parser.add_argument("-p", "--port", default="/dev/ttyUSB0")
    parser.add_argument("-b", "--baud", type=int, default=115200)
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="seconds to wait for one ok; slow feeds need this high")
    parser.add_argument("--feed", type=float, default=None,
                        help="override every drawing feed rate, mm/min")
    parser.add_argument("--console", action="store_true",
                        help="type commands interactively instead of sending a file")
    args = parser.parse_args()

    if not args.console and args.gcode is None:
        parser.error("give a G-code file, or use --console")
    if args.gcode and not args.gcode.exists():
        sys.exit(f"no such file: {args.gcode}")

    print(f"opening {args.port} at {args.baud}")
    try:
        plotter = Plotter(args.port, args.baud, args.timeout)
    except serial.SerialException as exc:
        sys.exit(f"could not open {args.port}: {exc}")
    plotter.wait_for_boot()

    try:
        if args.console:
            print("type G-code or $HELP; blank line or Ctrl-D to quit")
            while True:
                try:
                    command = input("> ")
                except EOFError:
                    break
                if not command.strip():
                    break
                plotter.send(command)
        else:
            lines = args.gcode.read_text().splitlines()
            print(f"streaming {len(lines)} lines from {args.gcode}")
            if stream(plotter, lines, args.feed):
                print("done")
    except KeyboardInterrupt:
        print("\ninterrupted, lifting pen and releasing motors")
        plotter.shutdown()
    finally:
        plotter.shutdown()
        plotter.close()


if __name__ == "__main__":
    main()
