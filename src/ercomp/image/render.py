"""Truecolor solid-block terminal renderers (half / quad / sextant; optional braille)."""

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

# 2×3 sextants — solid squares (no braille gaps). Bit order LSB = bottom-right:
#   32 16
#    8  4
#    2  1
# Index 0..63 → glyph (space / U+1FB00… / half / full). From img2blocks (scruss).
_SEXTANTS = (
    "\u00a0"  # 0 empty (NBSP keeps cell)
    "\U0001fb1e"  # 1
    "\U0001fb0f"  # 2
    "\U0001fb2d"  # 3
    "\U0001fb07"  # 4
    "\U0001fb26"  # 5
    "\U0001fb16"  # 6
    "\U0001fb35"  # 7
    "\U0001fb03"  # 8
    "\U0001fb22"  # 9
    "\U0001fb13"  # 10
    "\U0001fb31"  # 11
    "\U0001fb0b"  # 12
    "\U0001fb29"  # 13
    "\U0001fb1a"  # 14
    "\U0001fb39"  # 15
    "\U0001fb01"  # 16
    "\U0001fb20"  # 17
    "\U0001fb11"  # 18
    "\U0001fb2f"  # 19
    "\U0001fb09"  # 20
    "\u2590"  # 21 RIGHT HALF BLOCK
    "\U0001fb18"  # 22
    "\U0001fb37"  # 23
    "\U0001fb05"  # 24
    "\U0001fb24"  # 25
    "\U0001fb14"  # 26
    "\U0001fb33"  # 27
    "\U0001fb0d"  # 28
    "\U0001fb2b"  # 29
    "\U0001fb1c"  # 30
    "\U0001fb3b"  # 31
    "\U0001fb00"  # 32
    "\U0001fb1f"  # 33
    "\U0001fb10"  # 34
    "\U0001fb2e"  # 35
    "\U0001fb08"  # 36
    "\U0001fb27"  # 37
    "\U0001fb17"  # 38
    "\U0001fb36"  # 39
    "\U0001fb04"  # 40
    "\U0001fb23"  # 41
    "\u258c"  # 42 LEFT HALF BLOCK
    "\U0001fb32"  # 43
    "\U0001fb0c"  # 44
    "\U0001fb2a"  # 45
    "\U0001fb1b"  # 46
    "\U0001fb3a"  # 47
    "\U0001fb02"  # 48
    "\U0001fb21"  # 49
    "\U0001fb12"  # 50
    "\U0001fb30"  # 51
    "\U0001fb0a"  # 52
    "\U0001fb28"  # 53
    "\U0001fb19"  # 54
    "\U0001fb38"  # 55
    "\U0001fb06"  # 56
    "\U0001fb25"  # 57
    "\U0001fb15"  # 58
    "\U0001fb34"  # 59
    "\U0001fb0e"  # 60
    "\U0001fb2c"  # 61
    "\U0001fb1d"  # 62
    "\u2588"  # 63 FULL BLOCK
)


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
    style: str = "half",
) -> tuple[int, int]:
    """
    Target pixel size for a given blocks style.

    - half:    1×2 samples / cell (▀) — solid, truecolor (default)
    - quad:    2×2 samples / cell — solid squares
    - sextant: 2×3 samples / cell — densest solid (needs sextant glyphs)
    - braille: 2×4 samples / cell (⣿) — denser but dotted gaps
    """
    if img_w <= 0 or img_h <= 0:
        return 1, 1

    max_cols = max(1, max_cols)
    max_rows = max(1, max_rows)
    style = (style or "half").lower()

    if style == "quad":
        max_pw, max_ph = max_cols * 2, max_rows * 2
        align_w, align_h = 2, 2
    elif style == "sextant":
        max_pw, max_ph = max_cols * 2, max_rows * 3
        align_w, align_h = 2, 3
    elif style == "braille":
        max_pw, max_ph = max_cols * 2, max_rows * 4
        align_w, align_h = 2, 4
    else:  # half
        max_pw, max_ph = max_cols, max_rows * 2
        align_w, align_h = 1, 2

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


def _avg_rgb(colors: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    if not colors:
        return 0, 0, 0
    n = len(colors)
    return (
        sum(c[0] for c in colors) // n,
        sum(c[1] for c in colors) // n,
        sum(c[2] for c in colors) // n,
    )


def _threshold_cell(
    samples: list[tuple[int, int, int, float]],
) -> tuple[int, tuple[int, int, int], tuple[int, int, int]]:
    """Split samples by luminance → bit mask + FG/BG averages."""
    mean = sum(s[3] for s in samples) / len(samples)
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
        fr, fg_, fb = _avg_rgb(on)
    else:
        fr, fg_, fb = _avg_rgb([(s[0], s[1], s[2]) for s in samples])
        bits = (1 << len(samples)) - 1
    br, bg_, bb = _avg_rgb(off) if off else (0, 0, 0)
    return bits, (fr, fg_, fb), (br, bg_, bb)


def render_halfblocks(
    img: Image.Image, width: int, height: int, *, fast: bool = False
) -> str:
    """Classic ▀ half-blocks (1×2 per cell) — solid fill, truecolor top/bottom."""
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
    """2×2 quadrant glyphs — solid squares, ~2× denser than half-blocks."""
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
            bits, (fr, fg_, fb), (br, bg_, bb) = _threshold_cell(samples)
            parts.append(f"{_fg(fr, fg_, fb)}{_bg(br, bg_, bb)}{_QUADS[bits]}")
        parts.append(_RESET)
        lines.append("".join(parts))
    return "\n".join(lines)


def render_sextants(
    img: Image.Image, width: int, height: int, *, fast: bool = False
) -> str:
    """2×3 solid sextants — densest gapless blocks (needs font/terminal support)."""
    rgba = img.convert("RGBA")
    resample = Image.Resampling.BILINEAR if fast else Image.Resampling.LANCZOS
    resized = rgba.resize((width, height), resample)
    pixels = resized.load()
    assert pixels is not None

    lines: list[str] = []
    for y in range(0, height, 3):
        parts: list[str] = []
        for x in range(0, width, 2):
            samples: list[tuple[int, int, int, float]] = []
            # Bit order for _SEXTANTS: row-major TL→BR with LSB at bottom-right
            # Collect in order: (0,0),(1,0),(0,1),(1,1),(0,2),(1,2) then remap.
            raw: list[tuple[int, int, int, float]] = []
            for dy in range(3):
                for dx in range(2):
                    xx, yy = x + dx, y + dy
                    if xx < width and yy < height:
                        r, g, b, a = _rgb_a(pixels[xx, yy])
                        if a < 128:
                            r = g = b = 0
                        raw.append((r, g, b, _lum(r, g, b)))
                    else:
                        raw.append((0, 0, 0, 0.0))
            # Remap to LSB=bottom-right packing used by lookup string:
            # indices in raw: 0=TL 1=TR 2=ML 3=MR 4=BL 5=BR
            # bit0=BR bit1=BL bit2=MR bit3=ML bit4=TR bit5=TL
            order = (5, 4, 3, 2, 1, 0)
            samples = [raw[i] for i in order]
            bits, (fr, fg_, fb), (br, bg_, bb) = _threshold_cell(samples)
            parts.append(f"{_fg(fr, fg_, fb)}{_bg(br, bg_, bb)}{_SEXTANTS[bits]}")
        parts.append(_RESET)
        lines.append("".join(parts))
    return "\n".join(lines)


def render_braille(
    img: Image.Image, width: int, height: int, *, fast: bool = False
) -> str:
    """
    Braille ⣿ cells (2×4 dots) — denser but fonts leave gaps between dots.
    Kept optional; not recommended for photos.
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
                fr, fg_, fb = _avg_rgb(on)
            else:
                fr, fg_, fb = _avg_rgb([(s[0], s[1], s[2]) for s in samples])
                pattern = 0xFF
            br, bg_, bb = _avg_rgb(off) if off else (0, 0, 0)
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
    style: str = "half",
    fast: bool = False,
) -> str:
    style = (style or "half").lower()
    if style == "quad":
        return render_quadrants(img, width, height, fast=fast)
    if style == "sextant":
        return render_sextants(img, width, height, fast=fast)
    if style == "braille":
        return render_braille(img, width, height, fast=fast)
    return render_halfblocks(img, width, height, fast=fast)


def cell_size(style: str) -> tuple[int, int]:
    """Image pixels covered by one terminal cell for this style."""
    style = (style or "half").lower()
    if style == "quad":
        return 2, 2
    if style == "sextant":
        return 2, 3
    if style == "braille":
        return 2, 4
    return 1, 2
