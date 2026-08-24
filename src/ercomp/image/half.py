"""Fast truecolor half-block renderer (stills + video)."""

from __future__ import annotations

from PIL import Image

_RESET = b"\x1b[0m"
_BLOCK = "▀".encode("utf-8")  # 3 bytes
_NL = b"\n"

# Soft cap for video sample cells when sixel is unavailable.
VIDEO_CELL_BUDGET = 12000


def budget_cells(cols: int, rows: int, *, budget: int | None = None) -> tuple[int, int]:
    """Shrink sample grid if terminal is huge (tiny font)."""
    if budget is None:
        try:
            from ercomp.config import load_config

            budget = int(load_config().cell_budget)
        except Exception:
            budget = VIDEO_CELL_BUDGET
    budget = max(1000, int(budget))
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


_FG_CACHE: dict[tuple[int, int, int], bytes] = {}
_BG_CACHE: dict[tuple[int, int, int], bytes] = {}
_BOTH_CACHE: dict[tuple[int, int, int, int, int, int], bytes] = {}


def _sgr_both(tr: int, tg: int, tb: int, br: int, bg: int, bb: int) -> bytes:
    k = (tr, tg, tb, br, bg, bb)
    b = _BOTH_CACHE.get(k)
    if b is None:
        b = f"\x1b[38;2;{tr};{tg};{tb};48;2;{br};{bg};{bb}m".encode("ascii")
        _BOTH_CACHE[k] = b
    return b


def _sgr_fg(tr: int, tg: int, tb: int) -> bytes:
    k = (tr, tg, tb)
    b = _FG_CACHE.get(k)
    if b is None:
        b = f"\x1b[38;2;{tr};{tg};{tb}m".encode("ascii")
        _FG_CACHE[k] = b
    return b


def _sgr_bg(br: int, bg: int, bb: int) -> bytes:
    k = (br, bg, bb)
    b = _BG_CACHE.get(k)
    if b is None:
        b = f"\x1b[48;2;{br};{bg};{bb}m".encode("ascii")
        _BG_CACHE[k] = b
    return b


def render_halfblocks_rgb(
    img: Image.Image,
    width: int,
    height: int,
    *,
    quant: int = 0,
    repeat_x: int = 1,
    repeat_y: int = 1,
) -> bytes:
    """Truecolor ▀ encoder → UTF-8 bytes (SGR-coalesced)."""
    data, w, h = _ensure_rgb(img, width, height)
    qx = max(1, int(repeat_x))
    qy = max(1, int(repeat_y))
    qstep = max(0, int(quant))

    out = bytearray()
    row_bytes = w * 3
    append = out.extend
    block = _BLOCK * qx if qx > 1 else _BLOCK

    for y in range(0, h, 2):
        prev_fg = (-1, -1, -1)
        prev_bg = (-1, -1, -1)
        top = y * row_bytes
        bot = (y + 1) * row_bytes if y + 1 < h else None
        line = bytearray()
        lapp = line.extend

        for x in range(w):
            i = top + x * 3
            tr, tg, tb = data[i], data[i + 1], data[i + 2]
            if bot is None:
                br = bg = bb = 0
            else:
                j = bot + x * 3
                br, bg, bb = data[j], data[j + 1], data[j + 2]

            if qstep:
                tr = tr - (tr % qstep)
                tg = tg - (tg % qstep)
                tb = tb - (tb % qstep)
                br = br - (br % qstep)
                bg = bg - (bg % qstep)
                bb = bb - (bb % qstep)

            fg = (tr, tg, tb)
            bgc = (br, bg, bb)
            if fg != prev_fg and bgc != prev_bg:
                lapp(_sgr_both(tr, tg, tb, br, bg, bb))
                prev_fg, prev_bg = fg, bgc
            elif fg != prev_fg:
                lapp(_sgr_fg(tr, tg, tb))
                prev_fg = fg
            elif bgc != prev_bg:
                lapp(_sgr_bg(br, bg, bb))
                prev_bg = bgc
            lapp(block)

        lapp(_RESET)
        if qy == 1:
            append(line)
            append(_NL)
        else:
            line += _NL
            for _ in range(qy):
                append(line)

    if out.endswith(_NL):
        del out[-1:]
    return bytes(out)


def render_halfblocks_rgb_str(
    img: Image.Image, width: int, height: int, **kwargs: object
) -> str:
    """str wrapper for stills / non-video callers."""
    return render_halfblocks_rgb(img, width, height, **kwargs).decode("utf-8")  # type: ignore[arg-type]
