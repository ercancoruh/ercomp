"""Truecolor half-block terminal renderer."""

from __future__ import annotations

from PIL import Image


def term_size() -> tuple[int, int]:
    """Return (columns, rows) of the current terminal, with sane fallbacks."""
    try:
        import shutil

        cols, rows = shutil.get_terminal_size(fallback=(80, 24))
        return max(1, cols), max(1, rows)
    except OSError:
        return 80, 24


def fit_size(
    img_w: int,
    img_h: int,
    max_cols: int,
    max_rows: int,
) -> tuple[int, int]:
    """
    Pixel size for rendering.

    Each terminal row shows 2 image rows (upper + lower half of ▀),
    so display height in rows = ceil(pixel_h / 2).
    """
    if img_w <= 0 or img_h <= 0:
        return 1, 1

    # Usable area: leave one row for the prompt after draw
    max_cols = max(1, max_cols)
    max_rows = max(1, max_rows)
    max_pixel_h = max_rows * 2

    scale = min(max_cols / img_w, max_pixel_h / img_h)
    out_w = max(1, int(img_w * scale))
    out_h = max(1, int(img_h * scale))
    # Prefer even height so ▀ pairs cleanly
    if out_h % 2:
        out_h = max(1, out_h - 1) if out_h > 1 else 1
    return out_w, out_h


def _rgb(px: tuple[int, ...] | int) -> tuple[int, int, int]:
    if isinstance(px, int):
        return px, px, px
    if len(px) >= 3:
        return int(px[0]), int(px[1]), int(px[2])
    v = int(px[0]) if px else 0
    return v, v, v


def _fg(r: int, g: int, b: int) -> str:
    return f"\x1b[38;2;{r};{g};{b}m"


def _bg(r: int, g: int, b: int) -> str:
    return f"\x1b[48;2;{r};{g};{b}m"


_RESET = "\x1b[0m"


def render_halfblocks(
    img: Image.Image, width: int, height: int, *, fast: bool = False
) -> str:
    """Render image as ANSI truecolor half-block art."""
    rgba = img.convert("RGBA")
    resample = Image.Resampling.BILINEAR if fast else Image.Resampling.LANCZOS
    resized = rgba.resize((width, height), resample)
    pixels = resized.load()
    assert pixels is not None

    bg = (0, 0, 0)
    lines: list[str] = []
    for y in range(0, height, 2):
        parts: list[str] = []
        for x in range(width):
            top = pixels[x, y]
            if y + 1 < height:
                bot = pixels[x, y + 1]
            else:
                bot = (0, 0, 0, 0)

            tr, tg, tb, ta = top[0], top[1], top[2], top[3]
            br, bg_, bb, ba = bot[0], bot[1], bot[2], bot[3]

            if ta < 128:
                tr, tg, tb = bg
            if ba < 128:
                br, bg_, bb = bg

            parts.append(f"{_fg(tr, tg, tb)}{_bg(br, bg_, bb)}▀")
        parts.append(_RESET)
        lines.append("".join(parts))
    return "\n".join(lines)
