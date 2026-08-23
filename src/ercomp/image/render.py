"""Truecolor block / braille terminal renderers (high-density text graphics)."""

from __future__ import annotations

from PIL import Image

# Braille dots (dx, dy) → bit in U+2800 pattern
#   1 4
#   2 5
#   3 6
#   7 8
_BRAILLE_BITS = (
    (0x01, 0x08),
    (0x02, 0x10),
    (0x04, 0x20),
    (0x40, 0x80),
)

# 2×2 quadrant glyphs: bits TL=1 TR=2 BL=4 BR=8
_QUADS = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"


def term_size() -> tuple[int, int]:
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
    *,
    style: str = "braille",
) -> tuple[int, int]:
    """
    Target pixel size for a given blocks style.

    - half:    1×2 samples / cell (▀)
    - quad:    2×2 samples / cell
    - braille: 2×4 samples / cell (⣿) — default, sharpest
    """
    if img_w <= 0 or img_h <= 0:
        return 1, 1

    max_cols = max(1, max_cols)
    max_rows = max(1, max_rows)
    style = (style or "braille").lower()

    if style == "half":
        max_pw, max_ph = max_cols, max_rows * 2
        align_w, align_h = 1, 2
    elif style == "quad":
        max_pw, max_ph = max_cols * 2, max_rows * 2
        align_w, align_h = 2, 2
    else:  # braille
        max_pw, max_ph = max_cols * 2, max_rows * 4
        align_w, align_h = 2, 4

    scale = min(max_pw / img_w, max_ph / img_h)
    out_w = max(align_w, int(img_w * scale))
    out_h = max(align_h, int(img_h * scale))
    out_w -= out_w % align_w
    out_h -= out_h % align_h
    return max(align_w, out_w), max(align_h, out_h)


def _rgb_a(px: tuple[int, ...] | int) -> tuple[int, int, int, int]:
    if isinstance(px, int):
        return px, px, px, 255
    if len(px) >= 4:
        return int(px[0]), int(px[1]), int(px[2]), int(px[3])
    if len(px) >= 3:
        return int(px[0]), int(px[1]), int(px[2]), 255
    v = int(px[0]) if px else 0
    return v, v, v, 255


def _lum(r: int, g: int, b: int) -> float:
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _fg(r: int, g: int, b: int) -> str:
    return f"\x1b[38;2;{r};{g};{b}m"


def _bg(r: int, g: int, b: int) -> str:
    return f"\x1b[48;2;{r};{g};{b}m"


_RESET = "\x1b[0m"


def render_halfblocks(
    img: Image.Image, width: int, height: int, *, fast: bool = False
) -> str:
    """Classic ▀ half-blocks (1×2 per cell)."""
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
            top = _rgb_a(pixels[x, y])
            bot = _rgb_a(pixels[x, y + 1]) if y + 1 < height else (0, 0, 0, 0)
            tr, tg, tb, ta = top
            br, bg_, bb, ba = bot
            if ta < 128:
                tr, tg, tb = bg
            if ba < 128:
                br, bg_, bb = bg
            parts.append(f"{_fg(tr, tg, tb)}{_bg(br, bg_, bb)}▀")
        parts.append(_RESET)
        lines.append("".join(parts))
    return "\n".join(lines)


def render_quadrants(
    img: Image.Image, width: int, height: int, *, fast: bool = False
) -> str:
    """2×2 quadrant glyphs — ~2× denser than half-blocks."""
    rgba = img.convert("RGBA")
    resample = Image.Resampling.BILINEAR if fast else Image.Resampling.LANCZOS
    resized = rgba.resize((width, height), resample)
    pixels = resized.load()
    assert pixels is not None

    lines: list[str] = []
    for y in range(0, height, 2):
        parts: list[str] = []
        for x in range(0, width, 2):
            samples: list[tuple[int, int, int, float]] = []
            for dy in (0, 1):
                for dx in (0, 1):
                    xx, yy = x + dx, y + dy
                    if xx < width and yy < height:
                        r, g, b, a = _rgb_a(pixels[xx, yy])
                        if a < 128:
                            r = g = b = 0
                        samples.append((r, g, b, _lum(r, g, b)))
                    else:
                        samples.append((0, 0, 0, 0.0))
            mean = sum(s[3] for s in samples) / 4.0
            bits = 0
            on: list[tuple[int, int, int]] = []
            off: list[tuple[int, int, int]] = []
            for i, (r, g, b, L) in enumerate(samples):
                if L >= mean:
                    bits |= 1 << i
                    on.append((r, g, b))
                else:
                    off.append((r, g, b))
            if on:
                fr = sum(c[0] for c in on) // len(on)
                fg_ = sum(c[1] for c in on) // len(on)
                fb = sum(c[2] for c in on) // len(on)
            else:
                fr = fg_ = fb = 0
            if off:
                br = sum(c[0] for c in off) // len(off)
                bg_ = sum(c[1] for c in off) // len(off)
                bb = sum(c[2] for c in off) // len(off)
            else:
                br = bg_ = bb = 0
            parts.append(f"{_fg(fr, fg_, fb)}{_bg(br, bg_, bb)}{_QUADS[bits]}")
        parts.append(_RESET)
        lines.append("".join(parts))
    return "\n".join(lines)


def render_braille(
    img: Image.Image, width: int, height: int, *, fast: bool = False
) -> str:
    """
    Braille ⣿ cells (2×4 dots) — ~4× the sample density of half-blocks.

    Each cell: FG = average of 'on' dots, BG = average of 'off' dots.
    """
    rgba = img.convert("RGBA")
    resample = Image.Resampling.BILINEAR if fast else Image.Resampling.LANCZOS
    resized = rgba.resize((width, height), resample)
    pixels = resized.load()
    assert pixels is not None

    lines: list[str] = []
    for y in range(0, height, 4):
        parts: list[str] = []
        for x in range(0, width, 2):
            samples: list[tuple[int, int, int, float]] = []
            for dy in range(4):
                for dx in range(2):
                    xx, yy = x + dx, y + dy
                    if xx < width and yy < height:
                        r, g, b, a = _rgb_a(pixels[xx, yy])
                        if a < 128:
                            r = g = b = 0
                        samples.append((r, g, b, _lum(r, g, b)))
                    else:
                        samples.append((0, 0, 0, 0.0))
            mean = sum(s[3] for s in samples) / len(samples)
            # Slight bias so midtones still form dots
            thresh = mean * 0.92
            pattern = 0
            on: list[tuple[int, int, int]] = []
            off: list[tuple[int, int, int]] = []
            i = 0
            for dy in range(4):
                for dx in range(2):
                    r, g, b, L = samples[i]
                    i += 1
                    if L >= thresh:
                        pattern |= _BRAILLE_BITS[dy][dx]
                        on.append((r, g, b))
                    else:
                        off.append((r, g, b))
            if not on and not off:
                parts.append(" ")
                continue
            if on:
                fr = sum(c[0] for c in on) // len(on)
                fg_ = sum(c[1] for c in on) // len(on)
                fb = sum(c[2] for c in on) // len(on)
            else:
                # all below threshold — use mean color as BG fill
                fr = sum(s[0] for s in samples) // len(samples)
                fg_ = sum(s[1] for s in samples) // len(samples)
                fb = sum(s[2] for s in samples) // len(samples)
                pattern = 0xFF
            if off:
                br = sum(c[0] for c in off) // len(off)
                bg_ = sum(c[1] for c in off) // len(off)
                bb = sum(c[2] for c in off) // len(off)
            else:
                br = bg_ = bb = 0
            ch = chr(0x2800 + pattern)
            parts.append(f"{_fg(fr, fg_, fb)}{_bg(br, bg_, bb)}{ch}")
        parts.append(_RESET)
        lines.append("".join(parts))
    return "\n".join(lines)


def render_blocks_art(
    img: Image.Image,
    width: int,
    height: int,
    *,
    style: str = "braille",
    fast: bool = False,
) -> str:
    style = (style or "braille").lower()
    if style == "half":
        return render_halfblocks(img, width, height, fast=fast)
    if style == "quad":
        return render_quadrants(img, width, height, fast=fast)
    return render_braille(img, width, height, fast=fast)


def cell_size(style: str) -> tuple[int, int]:
    """Image pixels covered by one terminal cell for this style."""
    style = (style or "braille").lower()
    if style == "half":
        return 1, 2
    if style == "quad":
        return 2, 2
    return 2, 4
