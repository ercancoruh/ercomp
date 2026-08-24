"""Truecolor half-block (▀) + sixel video graphics."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ercomp.image.chrome import FOOTER_ROWS, HEADER_ROWS, cup
from ercomp.image.term import TermGeometry, fit_pixels

if TYPE_CHECKING:
    from PIL import Image

_RESERVE = HEADER_ROWS + FOOTER_ROWS


def render_blocks(img: Image.Image, geo: TermGeometry, *, fast: bool = False) -> str:
    """
    Draw with solid ▀ half-blocks (truecolor FG top / BG bottom).

    Stills (fast=False): full cell grid, Lanczos, exact RGB.
    Interactive/zoom (fast=True): full grid, BOX resize, exact RGB.
    """
    from ercomp.image.half import render_halfblocks_rgb
    from ercomp.image.render import fit_size
    from PIL import Image as PILImage

    cols, rows = geo.usable_cells(reserve_rows=_RESERVE)
    out_w, out_h = fit_size(img.width, img.height, cols, rows, style="half")
    rgb = img if img.mode == "RGB" else img.convert("RGB")
    if rgb.size != (out_w, out_h):
        resample = PILImage.Resampling.BOX if fast else PILImage.Resampling.LANCZOS
        rgb = rgb.resize((out_w, out_h), resample)

    raw = render_halfblocks_rgb(rgb, out_w, out_h)
    art = raw.decode("utf-8")
    art_cols = out_w
    art_rows = art.count("\n") + 1 if art else 0
    top = HEADER_ROWS + max(0, (rows - art_rows) // 2)
    left = max(0, (cols - art_cols) // 2)
    lines = art.split("\n")
    pad = " " * left
    return "".join(f"{cup(top + i + 1, 1)}{pad}{line}" for i, line in enumerate(lines))


def _video_sample_grid(cols: int, rows: int, budget: int) -> tuple[int, int, int]:
    """Return (sample_cols, sample_rows, tile_scale) to stay under cell budget."""
    n = max(1, cols * rows)
    budget = max(1000, int(budget))
    if n <= budget:
        return cols, rows, 1
    import math

    scale = max(1, int(math.ceil(math.sqrt(n / budget))))
    return max(2, cols // scale), max(2, rows // scale), scale


def render_video_blocks(img: Image.Image, geo: TermGeometry, *, budget: int = 10000) -> bytes:
    """
    Truecolor half-block video.

    Uses the full cell grid when it fits under `budget`; otherwise samples and
    tiles so the frame still fills the screen (chunkier, but real-time on WT).
    """
    from ercomp.image.half import render_halfblocks_rgb
    from ercomp.image.render import fit_size
    from PIL import Image as PILImage

    cols, rows = geo.usable_cells(reserve_rows=_RESERVE)
    sc, sr, scale = _video_sample_grid(cols, rows, budget)
    out_w, out_h = fit_size(img.width, img.height, sc, sr, style="half")
    rgb = img if img.mode == "RGB" else img.convert("RGB")
    if rgb.size != (out_w, out_h):
        rgb = rgb.resize((out_w, out_h), PILImage.Resampling.BOX)

    # quant=0 → exact RGB (sixel's tiny palette was the color problem)
    body = render_halfblocks_rgb(
        rgb, out_w, out_h, quant=0, repeat_x=scale, repeat_y=scale
    )

    art_cols = out_w * scale
    art_rows = max(1, (out_h // 2) * scale)
    top = HEADER_ROWS + max(0, (rows - art_rows) // 2)
    left = max(0, (cols - art_cols) // 2)
    origin = cup(top + 1, max(1, left + 1)).encode("ascii")

    if left <= 0 and scale == 1:
        return origin + body

    parts = [origin]
    cdown_left = f"\n\x1b[{left + 1}G".encode("ascii")
    first = True
    for line in body.split(b"\n"):
        if first:
            parts.append(line)
            first = False
        else:
            parts.append(cdown_left)
            parts.append(line)
    return b"".join(parts)


def render_video_sixel(
    img: Image.Image,
    geo: TermGeometry,
    *,
    colors: int = 64,
    max_px: int = 0,
) -> bytes:
    """Pixel sixel video frame fitted to fill the terminal content band."""
    from ercomp.image.sixel import encode_sixel_rgb
    from PIL import Image as PILImage

    max_w, max_h = geo.usable_pixels(reserve_rows=_RESERVE)
    # Guard: if pixel probe failed, fall back to a reasonable window estimate
    if max_w < 80 or max_h < 60:
        max_w = max(max_w, geo.cols * 8)
        max_h = max(max_h, max(1, geo.rows - _RESERVE) * 16)

    if max_px and max_px > 0:
        long_edge = max(max_w, max_h)
        if long_edge > max_px:
            s = max_px / long_edge
            max_w = max(2, int(max_w * s))
            max_h = max(2, int(max_h * s))

    out_w, out_h = fit_pixels(img.width, img.height, max_w, max_h)
    out_h -= out_h % 6  # sixel bands are 6px tall
    out_w, out_h = max(2, out_w), max(6, out_h)

    rgb = img if img.mode == "RGB" else img.convert("RGB")
    if rgb.size != (out_w, out_h):
        rgb = rgb.resize((out_w, out_h), PILImage.Resampling.BOX)

    body = encode_sixel_rgb(rgb, out_w, out_h, colors=colors)
    # Place at top of content band, horizontally centered (1:1 pixel sixel)
    row, col = geo.content_origin(
        out_w, out_h, top_rows=HEADER_ROWS, bottom_rows=FOOTER_ROWS
    )
    # Prefer top alignment so letterbox sits below/ beside, not floating mid-screen
    row = HEADER_ROWS + 1
    return cup(row, col).encode("ascii") + body


def render_video(
    img: Image.Image,
    geo: TermGeometry,
    *,
    use_sixel: bool = False,
    budget: int = 12000,
    sixel_colors: int = 64,
    max_px: int = 0,
) -> bytes:
    """Video frame: sixel when available, else budgeted half-blocks."""
    if use_sixel:
        return render_video_sixel(img, geo, colors=sixel_colors, max_px=max_px)
    return render_video_blocks(img, geo, budget=budget)


def render(img: Image.Image, geo: TermGeometry, *, fast: bool = False) -> str:
    """Rasterize image as truecolor half-blocks (str)."""
    return render_blocks(img, geo, fast=fast)
