"""Terminal geometry and capability detection."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from enum import Enum


class Protocol(str, Enum):
    KITTY = "kitty"
    ITERM = "iterm"
    SIXEL = "sixel"
    BLOCKS = "blocks"


@dataclass(frozen=True)
class TermGeometry:
    cols: int
    rows: int
    px_width: int | None = None
    px_height: int | None = None

    @property
    def cell_px(self) -> tuple[int, int]:
        if self.px_width and self.px_height and self.cols and self.rows:
            return max(1, self.px_width // self.cols), max(1, self.px_height // self.rows)
        # Typical modern terminal cell
        return 10, 20

    def usable_pixels(self, reserve_rows: int = 0) -> tuple[int, int]:
        """Max drawable pixel area after reserving rows (e.g. header/footer)."""
        rows = max(1, self.rows - reserve_rows)
        cw, ch = self.cell_px
        if self.px_width and self.px_height:
            return max(1, self.px_width), max(1, (self.px_height * rows) // self.rows)
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
        # Clamp so image stays above footer
        max_row = max(1, self.rows - bottom_rows - cells_h + 1)
        row = min(max(row, top_rows + 1), max_row)
        return row, col


def geometry(fd: int | None = None) -> TermGeometry:
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
        # rows, cols, pixels_x, pixels_y
        if buf[0]:
            rows = int(buf[0])
        if buf[1]:
            cols = int(buf[1])
        if buf[2] and buf[3]:
            px_w, px_h = int(buf[2]), int(buf[3])
    except (OSError, ImportError, AttributeError):
        pass
    return TermGeometry(cols=cols, rows=rows, px_width=px_w, px_height=px_h)


def _env(name: str) -> str:
    return os.environ.get(name, "")


def detect_protocol(preferred: str | None = None) -> Protocol:
    """
    Pick the best available graphics protocol.

    Order: kitty → iterm → sixel → blocks
    Override: preferred arg, or ERCOMP_PROTOCOL env.
    """
    forced = (preferred or _env("ERCOMP_PROTOCOL") or "").strip().lower()
    if forced:
        try:
            return Protocol(forced)
        except ValueError as e:
            raise ValueError(
                f"unknown protocol: {forced!r} (kitty|iterm|sixel|blocks)"
            ) from e

    term = _env("TERM").lower()
    program = _env("TERM_PROGRAM")
    # Kitty graphics: Kitty, Ghostty, WezTerm, and some others
    if (
        _env("KITTY_WINDOW_ID")
        or _env("GHOSTTY_RESOURCES_DIR")
        or program in {"WezTerm", "ghostty", "Ghostty"}
        or "kitty" in term
        or term == "xterm-ghostty"
    ):
        return Protocol.KITTY

    if program == "iTerm.app" or _env("ITERM_SESSION_ID"):
        return Protocol.ITERM

    # WezTerm also speaks iTerm; Kitty branch already catches WezTerm.
    # Sixel: foot, mlterm, xterm-sixel, contour, etc.
    if (
        "sixel" in term
        or term in {"foot", "mlterm", "yaft-256color"}
        or program in {"Contour", "iTerm.app"}  # iTerm also sixel; kitty preferred above
        or _env("TERM_FEATURES").find("sixel") >= 0
    ):
        return Protocol.SIXEL

    # Windows Terminal: limited; prefer blocks unless ConPTY gains protocols
    if _env("WT_SESSION"):
        return Protocol.BLOCKS

    return Protocol.BLOCKS


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
