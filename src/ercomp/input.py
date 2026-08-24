"""Terminal input: keys + optional SGR mouse (Unix); msvcrt keys (Windows)."""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from types import TracebackType


# Enable / disable mouse (SGR 1006 + button-event tracking) — Unix / ConPTY
ENABLE_MOUSE = "\x1b[?1000h\x1b[?1002h\x1b[?1006h"
DISABLE_MOUSE = "\x1b[?1006l\x1b[?1002l\x1b[?1000l"

_IS_WIN = sys.platform == "win32"


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


class TerminalInput:
    """
    Cross-platform cbreak keyboard reader.

    Unix: termios + select (CSI arrows / SGR mouse).
    Windows: msvcrt (arrows via \\x00/\\xe0 prefix).
    """

    def __init__(self) -> None:
        self._fd: int | None = None
        self._old: list | None = None
        self._active = False

    def __enter__(self) -> TerminalInput:
        if _IS_WIN:
            self._active = True
            return self
        import termios
        import tty

        self._fd = sys.stdin.fileno()
        self._old = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        self._active = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        if not self._active:
            return
        self._active = False
        if _IS_WIN or self._fd is None or self._old is None:
            return
        try:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)
        except Exception:
            pass
        self._fd = None
        self._old = None

    def read(self, timeout: float | None = None) -> Event | None:
        if not self._active:
            return None
        if _IS_WIN:
            return _read_windows(timeout)
        assert self._fd is not None
        return read_event(self._fd, timeout)


def read_event(fd: int, timeout: float | None = None) -> Event | None:
    """
    Read one input event from a Unix fd in cbreak mode.
    timeout=None blocks; timeout=0 polls; else seconds.
    """
    if _IS_WIN:
        return _read_windows(timeout)

    import select

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


def _read_windows(timeout: float | None = None) -> Event | None:
    """Poll console keyboard via msvcrt."""
    import msvcrt

    def _wait() -> bool:
        if timeout is None:
            while not msvcrt.kbhit():
                time.sleep(0.02)
            return True
        deadline = time.monotonic() + max(0.0, timeout)
        while not msvcrt.kbhit():
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.01)
        return True

    if not _wait():
        return None

    ch = msvcrt.getwch()
    # Function / arrow keys: prefix \x00 or \xe0 then scan code
    if ch in ("\x00", "\xe0"):
        code = ord(msvcrt.getwch())
        arrows = {72: "up", 80: "down", 75: "left", 77: "right"}
        if code in arrows:
            return Event(kind="key", key=arrows[code])
        return Event(kind="unknown")

    if ch == "\r":
        return Event(kind="key", key="\n")
    return Event(kind="key", key=ch)


def _parse_sgr_mouse(fd: int) -> Event:
    """Parse rest of SGR mouse after \\x1b[<"""
    import select

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
