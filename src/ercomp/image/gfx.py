"""Encode / transmit images via terminal graphics protocols."""

from __future__ import annotations

import base64
import io
from typing import TYPE_CHECKING

from ercomp.image.chrome import FOOTER_ROWS, HEADER_ROWS, cup
from ercomp.image.term import Protocol, TermGeometry, fit_pixels

if TYPE_CHECKING:
    from PIL import Image

_KITTY_CHUNK = 4096
_RESERVE = HEADER_ROWS + FOOTER_ROWS
# Delete all Kitty placements before redraw (safe no-op elsewhere)
KITTY_DELETE_ALL = "\x1b_Ga=d,d=A\x1b\\"


def _png_bytes(img: Image.Image, *, fast: bool = False) -> bytes:
    buf = io.BytesIO()
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        out = img.convert("RGBA")
    else:
        out = img.convert("RGB")
    if fast:
        # Low compression for video / animation frame rate
        out.save(buf, format="PNG", optimize=False, compress_level=1)
    else:
        out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _ensure_fit(img: Image.Image, geo: TermGeometry, *, fast: bool = False) -> Image.Image:
    """Fit frame into content pixels (no-op if already sized by Viewport)."""
    from PIL import Image as PILImage

    max_w, max_h = geo.usable_pixels(reserve_rows=_RESERVE)
    tw, th = fit_pixels(img.width, img.height, max_w, max_h)
    if (tw, th) != img.size:
        resample = PILImage.Resampling.BILINEAR if fast else PILImage.Resampling.LANCZOS
        return img.resize((tw, th), resample=resample)
    return img


def _origin(geo: TermGeometry, px_w: int, px_h: int) -> str:
    row, col = geo.content_origin(
        px_w, px_h, top_rows=HEADER_ROWS, bottom_rows=FOOTER_ROWS
    )
    return cup(row, col)


def render_kitty(img: Image.Image, geo: TermGeometry, *, fast: bool = False) -> str:
    prepared = _ensure_fit(img, geo, fast=fast)
    data = _png_bytes(prepared, fast=fast)
    b64 = base64.standard_b64encode(data).decode("ascii")
    parts: list[str] = [KITTY_DELETE_ALL, _origin(geo, prepared.width, prepared.height)]
    first = True
    for i in range(0, len(b64), _KITTY_CHUNK):
        chunk = b64[i : i + _KITTY_CHUNK]
        more = 1 if i + _KITTY_CHUNK < len(b64) else 0
        if first:
            parts.append(f"\x1b_Ga=T,f=100,q=2,m={more};{chunk}\x1b\\")
            first = False
        else:
            parts.append(f"\x1b_Gm={more};{chunk}\x1b\\")
    return "".join(parts)


def render_iterm(img: Image.Image, geo: TermGeometry, *, fast: bool = False) -> str:
    prepared = _ensure_fit(img, geo, fast=fast)
    data = _png_bytes(prepared, fast=fast)
    b64 = base64.standard_b64encode(data).decode("ascii")
    return (
        _origin(geo, prepared.width, prepared.height)
        + f"\x1b]1337;File=inline=1;size={len(data)};"
        f"width={prepared.width}px;height={prepared.height}px;"
        f"preserveAspectRatio=1;name={base64.standard_b64encode(b'ercomp').decode()};"
        f"{b64}\x07"
    )


def render_sixel(img: Image.Image, geo: TermGeometry, *, fast: bool = False) -> str:
    """Pure-Python sixel — no chafa/libsixel required."""
    prepared = _ensure_fit(img, geo, fast=fast)
    prefix = _origin(geo, prepared.width, prepared.height)
    return prefix + _sixel_python(prepared, fast=fast)


def _sixel_python(img: Image.Image, *, fast: bool = False) -> str:
    from PIL import Image as PILImage

    rgb = img.convert("RGB")
    colors = 64 if fast else 256
    pal = rgb.quantize(colors=colors, method=PILImage.Quantize.MEDIANCUT)
    palette = pal.getpalette() or []
    w, h = pal.size
    pixels = pal.load()
    assert pixels is not None

    out: list[str] = ["\x1bPq"]
    ncolors = min(colors, len(palette) // 3)
    for i in range(ncolors):
        r, g, b = palette[i * 3], palette[i * 3 + 1], palette[i * 3 + 2]
        out.append(f"#{i};2;{r * 100 // 255};{g * 100 // 255};{b * 100 // 255}")

    for y0 in range(0, h, 6):
        band_colors: dict[int, list[int]] = {}
        band_h = min(6, h - y0)
        for y in range(band_h):
            for x in range(w):
                c = int(pixels[x, y0 + y])
                band_colors.setdefault(c, [0] * w)
                band_colors[c][x] |= 1 << y
        first_color = True
        for c, cols_bits in band_colors.items():
            if not first_color:
                out.append("$")
            first_color = False
            out.append(f"#{c}")
            i = 0
            while i < w:
                bits = cols_bits[i]
                ch = chr(63 + bits)
                run = 1
                while i + run < w and cols_bits[i + run] == bits and run < 255:
                    run += 1
                if run > 3:
                    out.append(f"!{run}{ch}")
                else:
                    out.append(ch * run)
                i += run
        out.append("-")
    out.append("\x1b\\")
    return "".join(out)


def render_blocks(img: Image.Image, geo: TermGeometry, *, fast: bool = False) -> str:
    from ercomp.image.render import fit_size, render_halfblocks

    cols, rows = geo.usable_cells(reserve_rows=_RESERVE)
    out_w, out_h = fit_size(img.width, img.height, cols, rows)
    art = render_halfblocks(img, out_w, out_h, fast=fast)
    art_rows = art.count("\n") + 1 if art else 0
    art_cols = out_w
    content_rows = rows
    top = HEADER_ROWS + max(0, (content_rows - art_rows) // 2)
    left = max(0, (cols - art_cols) // 2)
    lines = art.split("\n")
    pad = " " * left
    placed = [f"{cup(top + i + 1, 1)}{pad}{line}" for i, line in enumerate(lines)]
    return "".join(placed)


def render(
    img: Image.Image,
    geo: TermGeometry,
    protocol: Protocol,
    *,
    fast: bool = False,
) -> str:
    """Rasterize `img` with `protocol`. fast=True optimizes for video/anim FPS."""
    if protocol is Protocol.KITTY:
        return render_kitty(img, geo, fast=fast)
    if protocol is Protocol.ITERM:
        return render_iterm(img, geo, fast=fast)
    if protocol is Protocol.SIXEL:
        return render_sixel(img, geo, fast=fast)
    return render_blocks(img, geo, fast=fast)
