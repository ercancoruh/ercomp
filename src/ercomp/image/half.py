"""Fast truecolor block renderers for video (SGR-coalesced)."""

from __future__ import annotations

from PIL import Image

_RESET = "\x1b[0m"

# Same tables as render.py — keep in sync
_QUADS = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"
_SEXTANTS = (
    "\u00a0"
    "\U0001fb1e\U0001fb0f\U0001fb2d\U0001fb07\U0001fb26\U0001fb16\U0001fb35"
    "\U0001fb03\U0001fb22\U0001fb13\U0001fb31\U0001fb0b\U0001fb29\U0001fb1a\U0001fb39"
    "\U0001fb01\U0001fb20\U0001fb11\U0001fb2f\U0001fb09\u2590\U0001fb18\U0001fb37"
    "\U0001fb05\U0001fb24\U0001fb14\U0001fb33\U0001fb0d\U0001fb2b\U0001fb1c\U0001fb3b"
    "\U0001fb00\U0001fb1f\U0001fb10\U0001fb2e\U0001fb08\U0001fb27\U0001fb17\U0001fb36"
    "\U0001fb04\U0001fb23\u258c\U0001fb32\U0001fb0c\U0001fb2a\U0001fb1b\U0001fb3a"
    "\U0001fb02\U0001fb21\U0001fb12\U0001fb30\U0001fb0a\U0001fb28\U0001fb19\U0001fb38"
    "\U0001fb06\U0001fb25\U0001fb15\U0001fb34\U0001fb0e\U0001fb2c\U0001fb1d\u2588"
)

# Soft cap: beyond this, shrink art so full-frame redraw stays real-time
# (~120×50 = 6000; tiny-font 250×80 would otherwise flood the PTY)
VIDEO_CELL_BUDGET = 7200


def budget_cells(cols: int, rows: int, *, budget: int = VIDEO_CELL_BUDGET) -> tuple[int, int]:
    """Shrink usable cell grid if terminal is huge (tiny font)."""
    cols, rows = max(2, cols), max(2, rows)
    n = cols * rows
    if n <= budget:
        return cols, rows
    s = (budget / n) ** 0.5
    return max(24, int(cols * s)), max(14, int(rows * s))


def _ensure_rgb(img: Image.Image, width: int, height: int) -> tuple[bytes, int, int]:
    if img.mode != "RGB":
        img = img.convert("RGB")
    if img.size != (width, height):
        img = img.resize((width, height), Image.Resampling.BOX)
    return img.tobytes(), width, height


def _emit_sgr(
    parts: list[str],
    fr: int,
    fg: int,
    fb: int,
    br: int,
    bg: int,
    bb: int,
    prev: list[int | None],
) -> None:
    """Append FG/BG only when changed. prev = [fr,fg,fb,br,bg,bb]."""
    if prev[0] != fr or prev[1] != fg or prev[2] != fb:
        parts.append(f"\x1b[38;2;{fr};{fg};{fb}m")
        prev[0], prev[1], prev[2] = fr, fg, fb
    if prev[3] != br or prev[4] != bg or prev[5] != bb:
        parts.append(f"\x1b[48;2;{br};{bg};{bb}m")
        prev[3], prev[4], prev[5] = br, bg, bb


def render_halfblocks_rgb(img: Image.Image, width: int, height: int) -> str:
    """Truecolor ▀ — exact top/bottom RGB, SGR-coalesced."""
    data, w, h = _ensure_rgb(img, width, height)
    lines: list[str] = []
    row_bytes = w * 3
    prev: list[int | None] = [None] * 6

    for y in range(0, h, 2):
        parts: list[str] = []
        prev[:] = [None] * 6
        top = y * row_bytes
        bot = (y + 1) * row_bytes if y + 1 < h else None
        for x in range(w):
            i = top + x * 3
            tr, tg, tb = data[i], data[i + 1], data[i + 2]
            if bot is None:
                br = bg = bb = 0
            else:
                j = bot + x * 3
                br, bg, bb = data[j], data[j + 1], data[j + 2]
            _emit_sgr(parts, tr, tg, tb, br, bg, bb, prev)
            parts.append("▀")
        parts.append(_RESET)
        lines.append("".join(parts))
    return "\n".join(lines)


def _lum(r: int, g: int, b: int) -> int:
    return (54 * r + 183 * g + 19 * b) >> 8


def _split4(
    samples: list[tuple[int, int, int]],
) -> tuple[int, int, int, int, int, int, int]:
    """4 RGB samples → bits + FG/BG averages (luminance split)."""
    L = [_lum(r, g, b) for r, g, b in samples]
    mean = sum(L) / 4.0
    bits = 0
    on_r = on_g = on_b = on_n = 0
    off_r = off_g = off_b = off_n = 0
    for i, ((r, g, b), Lv) in enumerate(zip(samples, L)):
        if Lv >= mean:
            bits |= 1 << i
            on_r += r
            on_g += g
            on_b += b
            on_n += 1
        else:
            off_r += r
            off_g += g
            off_b += b
            off_n += 1
    if on_n == 0:
        bits = 15
        on_r = sum(s[0] for s in samples)
        on_g = sum(s[1] for s in samples)
        on_b = sum(s[2] for s in samples)
        on_n = 4
        off_n = 0
    fr, fg, fb = on_r // on_n, on_g // on_n, on_b // on_n
    if off_n:
        br, bg, bb = off_r // off_n, off_g // off_n, off_b // off_n
    else:
        br = bg = bb = 0
    return bits, fr, fg, fb, br, bg, bb


def render_quadblocks_rgb(img: Image.Image, width: int, height: int) -> str:
    """2×2 solid quadrants — ~2× denser than half, SGR-coalesced."""
    data, w, h = _ensure_rgb(img, width, height)
    lines: list[str] = []
    row_bytes = w * 3
    prev: list[int | None] = [None] * 6

    for y in range(0, h, 2):
        parts: list[str] = []
        prev[:] = [None] * 6
        for x in range(0, w, 2):
            samples: list[tuple[int, int, int]] = []
            for dy in (0, 1):
                yy = y + dy
                for dx in (0, 1):
                    xx = x + dx
                    if xx < w and yy < h:
                        i = yy * row_bytes + xx * 3
                        samples.append((data[i], data[i + 1], data[i + 2]))
                    else:
                        samples.append((0, 0, 0))
            bits, fr, fg, fb, br, bg, bb = _split4(samples)
            _emit_sgr(parts, fr, fg, fb, br, bg, bb, prev)
            parts.append(_QUADS[bits])
        parts.append(_RESET)
        lines.append("".join(parts))
    return "\n".join(lines)


def _split6(
    samples: list[tuple[int, int, int]],
) -> tuple[int, int, int, int, int, int, int]:
    """6 RGB samples in sextant bit order → bits + FG/BG."""
    L = [_lum(r, g, b) for r, g, b in samples]
    mean = sum(L) / 6.0
    bits = 0
    on_r = on_g = on_b = on_n = 0
    off_r = off_g = off_b = off_n = 0
    for i, ((r, g, b), Lv) in enumerate(zip(samples, L)):
        if Lv >= mean:
            bits |= 1 << i
            on_r += r
            on_g += g
            on_b += b
            on_n += 1
        else:
            off_r += r
            off_g += g
            off_b += b
            off_n += 1
    if on_n == 0:
        bits = 63
        on_r = sum(s[0] for s in samples)
        on_g = sum(s[1] for s in samples)
        on_b = sum(s[2] for s in samples)
        on_n = 6
        off_n = 0
    fr, fg, fb = on_r // on_n, on_g // on_n, on_b // on_n
    if off_n:
        br, bg, bb = off_r // off_n, off_g // off_n, off_b // off_n
    else:
        br = bg = bb = 0
    return bits, fr, fg, fb, br, bg, bb


def render_sextantblocks_rgb(img: Image.Image, width: int, height: int) -> str:
    """2×3 solid sextants — densest gapless blocks, SGR-coalesced."""
    data, w, h = _ensure_rgb(img, width, height)
    lines: list[str] = []
    row_bytes = w * 3
    prev: list[int | None] = [None] * 6

    for y in range(0, h, 3):
        parts: list[str] = []
        prev[:] = [None] * 6
        for x in range(0, w, 2):
            # raw row-major: TL TR ML MR BL BR
            raw: list[tuple[int, int, int]] = []
            for dy in range(3):
                yy = y + dy
                for dx in range(2):
                    xx = x + dx
                    if xx < w and yy < h:
                        i = yy * row_bytes + xx * 3
                        raw.append((data[i], data[i + 1], data[i + 2]))
                    else:
                        raw.append((0, 0, 0))
            # bit0=BR bit1=BL bit2=MR bit3=ML bit4=TR bit5=TL
            order = (5, 4, 3, 2, 1, 0)
            samples = [raw[i] for i in order]
            bits, fr, fg, fb, br, bg, bb = _split6(samples)
            _emit_sgr(parts, fr, fg, fb, br, bg, bb, prev)
            parts.append(_SEXTANTS[bits])
        parts.append(_RESET)
        lines.append("".join(parts))
    return "\n".join(lines)


def render_blocks_rgb(img: Image.Image, width: int, height: int, *, style: str) -> str:
    style = (style or "half").lower()
    if style == "quad":
        return render_quadblocks_rgb(img, width, height)
    if style == "sextant":
        return render_sextantblocks_rgb(img, width, height)
    return render_halfblocks_rgb(img, width, height)
