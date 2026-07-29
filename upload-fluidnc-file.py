#!/usr/bin/env python3
"""Upload one file to FluidNC local storage via XMODEM-1K.

Usage:
  /home/priyanshuchawda/.fluidnc_venv/bin/python upload-fluidnc-file.py \
      /dev/ttyUSB0 config.yaml
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import serial
from xmodem import XMODEM


def usage() -> None:
    print(f"Usage: {Path(sys.argv[0]).name} SERIAL_PORT FILE", file=sys.stderr)


if len(sys.argv) != 3:
    usage()
    raise SystemExit(2)

port = sys.argv[1]
file_path = Path(sys.argv[2]).resolve()
if not file_path.is_file():
    print(f"File not found: {file_path}", file=sys.stderr)
    raise SystemExit(2)

remote_name = file_path.name

with serial.Serial(port, 115200, timeout=1, write_timeout=2) as connection:
    connection.reset_input_buffer()
    connection.write(f"$XModem/Receive={remote_name}\r\n".encode())
    connection.flush()

    received = bytearray()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        chunk = connection.read(128)
        if chunk:
            received.extend(chunk)
            if b"C" in chunk:
                break

    print(received.decode(errors="replace"), end="")
    if b"C" not in received:
        raise RuntimeError("FluidNC did not start XMODEM receive mode")

    def getc(size: int, timeout: int = 1) -> bytes | None:
        data = connection.read(size)
        return data or None

    def putc(data: bytes, timeout: int = 1) -> int:
        return connection.write(data)

    modem = XMODEM(getc, putc, mode="xmodem1k")
    with file_path.open("rb") as source:
        if not modem.send(source, retry=16, timeout=5):
            raise RuntimeError("XMODEM transfer failed")

    time.sleep(1)
    response = connection.read(2048)
    print(response.decode(errors="replace"), end="")
    connection.write(f"$Config/Filename={remote_name}\r\n$bye\r\n".encode())
    connection.flush()
    time.sleep(2)
    print(connection.read(4096).decode(errors="replace"), end="")

print(f"Uploaded and activated {remote_name}")
