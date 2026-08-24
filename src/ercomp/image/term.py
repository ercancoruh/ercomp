"""Terminal geometry and capability detection."""

from __future__ import annotations

import os
import re
import shutil
import sys
import time
from dataclasses import dataclass


# Cache: (cols, rows) → (px_w, px_h) from CSI 14/16 t
_probe_cache: tuple[int, int, int, int] | None = None


@dataclass(frozen=True)
class TermGeometry:
    cols: int
    rows: int
    px_width: int | None = None
    px_height: int | None = None

    @property
    def cell_px(self) -> tuple[int, int]:
        if self.px_width and self.px_height and self.cols and self.rows:
            cw = max(1, self.px_width // self.cols)
            ch = max(1, self.px_height // self.rows)
            if cw >= 1 and ch >= 1:
                return cw, ch
        return 8, 16

    def usable_pixels(self, reserve_rows: int = 0) -> tuple[int, int]:
        """Max drawable pixel area after reserving rows (e.g. header/footer)."""
        rows = max(1, self.rows - reserve_rows)
        if self.px_width and self.px_height and self.rows > 0:
            # Prefer window pixels directly (avoids cell_px integer truncation)
            h = max(1, int(self.px_height * rows / self.rows))
            return max(1, int(self.px_width)), h
        cw, ch = self.cell_px
        return max(1, self.cols * cw), max(1, rows * ch)

    def usable_cells(self, reserve_rows: int = 0) -> tuple[int, int]:
        return max(1, self.cols), max(1, self.rows - reserve_rows)

    def content_origin(
        self,
        px_w: int,
        px_h: int,
        *,
        top_rows: int = 0,
        bottom_rows: int = 0,
    ) -> tuple[int, int]:
        """1-based (row, col) to center an image in the content band."""
        cw, ch = self.cell_px
        cells_w = max(1, (px_w + cw - 1) // cw)
        cells_h = max(1, (px_h + ch - 1) // ch)
        content_rows = max(1, self.rows - top_rows - bottom_rows)
        col = max(1, (self.cols - cells_w) // 2 + 1)
        row = top_rows + max(0, (content_rows - cells_h) // 2) + 1
        max_row = max(1, self.rows - bottom_rows - cells_h + 1)
        row = min(max(row, top_rows + 1), max_row)
        return row, col


def geometry(*, probe: bool = False, fd: int | None = None) -> TermGeometry:
    """
    Current terminal size.

    probe=True asks the terminal (CSI 14/16 t) for real pixel size when available.
    """
    global _probe_cache

    cols, rows = shutil.get_terminal_size(fallback=(80, 24))
    cols, rows = max(1, cols), max(1, rows)
    px_w = px_h = None

    try:
        import array
        import fcntl
        import termios

        target = sys.stdout.fileno() if fd is None else fd
        buf = array.array("H", [0, 0, 0, 0])
        fcntl.ioctl(target, termios.TIOCGWINSZ, buf)
        if buf[0]:
            rows = int(buf[0])
        if buf[1]:
            cols = int(buf[1])
        if buf[2] and buf[3]:
            px_w, px_h = int(buf[2]), int(buf[3])
    except (OSError, ImportError, AttributeError):
        pass

    if probe and sys.stdout.isatty() and sys.stdin.isatty():
        if (
            _probe_cache is not None
            and _probe_cache[0] == cols
            and _probe_cache[1] == rows
        ):
            px_w, px_h = _probe_cache[2], _probe_cache[3]
        else:
            probed = _csi_probe_pixels(cols, rows)
            if probed:
                px_w, px_h = probed
                _probe_cache = (cols, rows, px_w, px_h)

    if px_w is None or px_h is None:
        if (
            _probe_cache is not None
            and _probe_cache[0] == cols
            and _probe_cache[1] == rows
        ):
            px_w, px_h = _probe_cache[2], _probe_cache[3]
        else:
            win = _windows_console_pixels(cols, rows)
            if win:
                px_w, px_h = win

    return TermGeometry(cols=cols, rows=rows, px_width=px_w, px_height=px_h)


def geometry_retain(prev: TermGeometry) -> TermGeometry:
    """Fast resize check — keep probed pixels unless cols/rows changed."""
    g = geometry(probe=False)
    if g.cols == prev.cols and g.rows == prev.rows:
        if prev.px_width and prev.px_height:
            return TermGeometry(g.cols, g.rows, prev.px_width, prev.px_height)
        return prev
    # Size changed — re-probe
    return geometry(probe=True)


def clear_geometry_cache() -> None:
    global _probe_cache
    _probe_cache = None


def _csi_probe_pixels(cols: int, rows: int) -> tuple[int, int] | None:
    """
    Query window (CSI 14 t) and cell (CSI 16 t) pixel size.
    Returns window pixels, or cell×grid if only cell reply arrives.
    """
    try:
        sys.stdout.write("\x1b[14t\x1b[16t")
        sys.stdout.flush()
    except OSError:
        return None

    raw = _read_terminal_replies(0.15)
    if not raw:
        return None

    # CSI 4 ; height ; width t  — text area in pixels
    m = re.search(r"\x1b\[4;(\d+);(\d+)t", raw)
    if m:
        h, w = int(m.group(1)), int(m.group(2))
        if w >= cols and h >= rows:
            return w, h

    # CSI 6 ; cell_height ; cell_width t
    m = re.search(r"\x1b\[6;(\d+);(\d+)t", raw)
    if m:
        ch, cw = int(m.group(1)), int(m.group(2))
        if cw > 0 and ch > 0:
            return cols * cw, rows * ch

    return None


def _read_terminal_replies(timeout: float) -> str:
    deadline = time.monotonic() + timeout
    buf = ""

    if sys.platform == "win32":
        import msvcrt

        while time.monotonic() < deadline:
            if msvcrt.kbhit():
                while msvcrt.kbhit():
                    buf += msvcrt.getwch()
                if "t" in buf and "\x1b[" in buf:
                    time.sleep(0.03)
                    while msvcrt.kbhit():
                        buf += msvcrt.getwch()
                    break
            else:
                time.sleep(0.01)
        return buf

    import select

    fd = sys.stdin.fileno()
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if not select.select([fd], [], [], min(0.04, remaining))[0]:
            if buf:
                break
            continue
        try:
            chunk = os.read(fd, 512).decode("latin1", errors="replace")
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        if "t" in buf:
            if select.select([fd], [], [], 0.03)[0]:
                try:
                    buf += os.read(fd, 512).decode("latin1", errors="replace")
                except OSError:
                    pass
            break
    return buf


def _windows_console_pixels(cols: int, rows: int) -> tuple[int, int] | None:
    """Fallback: console font metrics (often wrong under WT DPI — prefer CSI probe)."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class COORD(ctypes.Structure):
            _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]

        class CONSOLE_FONT_INFOEX(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.ULONG),
                ("nFont", wintypes.DWORD),
                ("dwFontSize", COORD),
                ("FontFamily", wintypes.UINT),
                ("FontWeight", wintypes.UINT),
                ("FaceName", wintypes.WCHAR * 32),
            ]

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        info = CONSOLE_FONT_INFOEX()
        info.cbSize = ctypes.sizeof(CONSOLE_FONT_INFOEX)
        if not kernel32.GetCurrentConsoleFontEx(handle, False, ctypes.byref(info)):
            return None
        cw, ch = int(info.dwFontSize.X), int(info.dwFontSize.Y)
        if cw <= 0 or ch <= 0 or cw > 48 or ch > 96:
            return None
        return cols * cw, rows * ch
    except Exception:
        return None


def fit_pixels(
    img_w: int,
    img_h: int,
    max_w: int,
    max_h: int,
) -> tuple[int, int]:
    """Scale image to fit inside max_w×max_h, preserving aspect (may upscale)."""
    if img_w <= 0 or img_h <= 0:
        return 1, 1
    max_w, max_h = max(1, max_w), max(1, max_h)
    scale = min(max_w / img_w, max_h / img_h)
    return max(1, int(img_w * scale)), max(1, int(img_h * scale))
