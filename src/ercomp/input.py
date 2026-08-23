"""Terminal input: keys + optional SGR mouse."""

from __future__ import annotations

import os
import select
from dataclasses import dataclass


# Enable / disable mouse (SGR 1006 + button-event tracking)
ENABLE_MOUSE = "\x1b[?1000h\x1b[?1002h\x1b[?1006h"
DISABLE_MOUSE = "\x1b[?1006l\x1b[?1002l\x1b[?1000l"


@dataclass
class Event:
    kind: str  # key|wheel|drag|click|unknown
    key: str = ""
    row: int = 0
    col: int = 0
    button: int = 0
    pressed: bool = False
    dx: int = 0
    dy: int = 0


def read_event(fd: int, timeout: float | None = None) -> Event | None:
    """
    Read one input event.
    timeout=None blocks; timeout=0 polls; else seconds.
    """
    if timeout is None:
        ready = True
    else:
        ready = bool(select.select([fd], [], [], max(0.0, timeout))[0])
    if not ready:
        return None

    ch = os.read(fd, 1).decode("latin1", errors="replace")
    if ch != "\x1b":
        return Event(kind="key", key=ch)

    # CSI or mouse
    if not select.select([fd], [], [], 0.05)[0]:
        return Event(kind="key", key="\x1b")
    nxt = os.read(fd, 1).decode("latin1", errors="replace")

    # SGR mouse: \x1b[<b;x;yM or m
    if nxt == "[":
        if not select.select([fd], [], [], 0.05)[0]:
            return Event(kind="key", key="\x1b")
        peek = os.read(fd, 1).decode("latin1", errors="replace")
        if peek == "<":
            return _parse_sgr_mouse(fd)
        # arrow / other CSI — collect until letter
        buf = peek
        while True:
            if buf and buf[-1].isalpha():
                break
            if not select.select([fd], [], [], 0.05)[0]:
                break
            buf += os.read(fd, 1).decode("latin1", errors="replace")
            if len(buf) > 16:
                break
        arrow = {"A": "up", "B": "down", "C": "right", "D": "left"}.get(buf[-1:], "")
        if arrow:
            return Event(kind="key", key=arrow)
        return Event(kind="key", key="\x1b")

    return Event(kind="key", key="\x1b")


def _parse_sgr_mouse(fd: int) -> Event:
    """Parse rest of SGR mouse after \\x1b[<"""
    buf = ""
    while True:
        if not select.select([fd], [], [], 0.05)[0]:
            break
        c = os.read(fd, 1).decode("latin1", errors="replace")
        buf += c
        if c in "Mm":
            break
        if len(buf) > 32:
            break
    pressed = buf.endswith("M")
    body = buf[:-1] if buf else ""
    parts = body.split(";")
    try:
        btn = int(parts[0]) if parts else 0
        col = int(parts[1]) if len(parts) > 1 else 0
        row = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        return Event(kind="unknown")

    # wheel
    if btn in (64, 65, 66, 67):
        return Event(
            kind="wheel",
            button=btn,
            col=col,
            row=row,
            key="zoom_in" if btn in (64, 66) else "zoom_out",
        )
    # motion with button (drag) — bit 32
    if btn >= 32:
        return Event(
            kind="drag",
            button=btn - 32,
            col=col,
            row=row,
            pressed=True,
        )
    return Event(kind="click", button=btn, col=col, row=row, pressed=pressed)
