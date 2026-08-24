"""Truecolor half-block (▀) terminal graphics — photos and video."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ercomp.image.chrome import FOOTER_ROWS, HEADER_ROWS, cup
from ercomp.image.term import TermGeometry

if TYPE_CHECKING:
    from PIL import Image

_RESERVE = HEADER_ROWS + FOOTER_ROWS


def render_blocks(img: Image.Image, geo: TermGeometry, *, fast: bool = False) -> str:
    """
    Draw with solid ▀ half-blocks (truecolor FG top / BG bottom).

    fast=True: BOX resize + SGR coalesce + soft cell budget (video/anim).
    fast=False: LANCZOS resize, full cell grid (stills).
    """
    from ercomp.image.half import budget_cells, render_halfblocks_rgb
    from ercomp.image.render import fit_size
    from PIL import Image as PILImage

    full_cols, full_rows = geo.usable_cells(reserve_rows=_RESERVE)
    cols, rows = full_cols, full_rows
    if fast:
        cols, rows = budget_cells(cols, rows)

    out_w, out_h = fit_size(img.width, img.height, cols, rows, style="half")
    rgb = img if img.mode == "RGB" else img.convert("RGB")
    if rgb.size != (out_w, out_h):
        resample = PILImage.Resampling.BOX if fast else PILImage.Resampling.LANCZOS
        rgb = rgb.resize((out_w, out_h), resample)

    art = render_halfblocks_rgb(rgb, out_w, out_h)
    art_cols = out_w
    art_rows = art.count("\n") + 1 if art else 0
    top = HEADER_ROWS + max(0, (full_rows - art_rows) // 2)
    left = max(0, (full_cols - art_cols) // 2)
    lines = art.split("\n")
    pad = " " * left
    return "".join(f"{cup(top + i + 1, 1)}{pad}{line}" for i, line in enumerate(lines))


def render(img: Image.Image, geo: TermGeometry, *, fast: bool = False) -> str:
    """Rasterize image as truecolor half-blocks."""
    return render_blocks(img, geo, fast=fast)
