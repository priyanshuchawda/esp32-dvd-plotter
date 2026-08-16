#!/usr/bin/env python3
"""Send commands to the Uno bring-up sketch and print what comes back.

    tools/uno_console.py x 20
    tools/uno_console.py s 60 x 40 y 40 x -40 y -40
    tools/uno_console.py            # interactive

Opening the port resets the board once. Put speed + moves in the same
invocation so the reset does not wipe the speed setting between steps.
"""

from __future__ import annotations

import argparse
import sys
import time

try:
    import serial
except ImportError:
    sys.exit("pyserial is required: pip install pyserial")


def drain(port, settle=0.3, hard_limit=30.0):
    """Print replies until the board goes quiet, with a hard ceiling."""
    deadline = time.time() + settle
    hard = time.time() + hard_limit
    while time.time() < deadline and time.time() < hard:
        line = port.readline()
        if line:
            print(line.decode(errors="replace").rstrip())
            deadline = time.time() + settle


def parse_commands(tokens):
    """Turn ['s','60','x','40','y','-40'] into ['s 60','x 40','y -40'].

    Also accepts one shell-blob like 's 60 x 40' (zsh does not word-split
    unquoted variables) and semicolon-separated lists.
    """
    if not tokens:
        return []
    joined = " ".join(tokens)
    if ";" in joined:
        return [part.strip() for part in joined.split(";") if part.strip()]

    # Flatten so a single argv blob still splits into words.
    words = joined.split()
    commands = []
    i = 0
    while i < len(words):
        head = words[i]
        if len(head) == 1 and head.lower() in "xy?sr12":
            if i + 1 < len(words) and words[i + 1][:1] in "-0123456789":
                commands.append(f"{head} {words[i + 1]}")
                i += 2
            else:
                commands.append(head)
                i += 1
        else:
            commands.append(head)
            i += 1
    return commands


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="*", help="e.g. s 60 x 40 y 40")
    parser.add_argument("-p", "--port", default="/dev/ttyACM0")
    parser.add_argument("-b", "--baud", type=int, default=9600)
    args = parser.parse_args()

    with serial.Serial(args.port, args.baud, timeout=0.2) as port:
        time.sleep(2)
        drain(port, settle=0.5, hard_limit=5.0)
        port.reset_input_buffer()

        if args.command:
            for command in parse_commands(args.command):
                print(f"> {command}")
                send(port, command)
            send(port, "r", quiet=True)
            return

        print("Type commands, '?' for the list, Ctrl-D to quit.")
        try:
            while True:
                try:
                    line = input("> ").strip()
                except EOFError:
                    break
                if line:
                    send(port, line)
        finally:
            send(port, "r", quiet=True)


def send(port, command, quiet=False):
    port.write((command + "\n").encode())
    port.flush()
    if quiet:
        drain(port, settle=0.3, hard_limit=3.0)
        return

    first = command[:1].lower()
    if first in ("x", "y"):
        hard = time.time() + 90.0
        while time.time() < hard:
            line = port.readline()
            if not line:
                continue
            text = line.decode(errors="replace").rstrip()
            print(text)
            if text.startswith("done") or text.startswith("zero"):
                return
        print("(timed out waiting for done)", file=sys.stderr)
        return

    drain(port, settle=0.5, hard_limit=10.0)


if __name__ == "__main__":
    main()
