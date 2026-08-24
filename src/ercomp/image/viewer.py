"""Open and display still / animated images in the terminal."""

from __future__ import annotations

from pathlib import Path

from ercomp.config import Config, load_config
from ercomp.detect import may_be_animated
from ercomp.image.anim import is_animated, play_animated
from ercomp.image.loader import ImageOpenError, open_image
from ercomp.image.session import view_fullscreen
from ercomp.image.term import geometry
from ercomp.playlist import Nav

__all__ = ["ImageOpenError", "image_info", "open_image", "show_image"]


def image_info(path: Path) -> str:
    img = open_image(path)
    fmt = img.format or "?"
    mode = img.mode
    w, h = img.size
    size_b = path.stat().st_size
    geo = geometry()
    px = f"{geo.px_width}×{geo.px_height}" if geo.px_width else "unknown"
    anim = ""
    if getattr(img, "is_animated", False):
        anim = f"\n  frames   : {getattr(img, 'n_frames', '?')}"
    return (
        f"{path.name}\n"
        f"  format   : {fmt}\n"
        f"  size     : {w}×{h}\n"
        f"  mode     : {mode}{anim}\n"
        f"  file     : {size_b} bytes\n"
        f"  path     : {path.resolve()}\n"
        f"  graphics : truecolor half-blocks\n"
        f"  term     : {geo.cols}×{geo.rows} cells, {px} px"
    )


def show_image(
    path: Path,
    *,
    dump: bool = False,
    cfg: Config | None = None,
) -> Nav:
    """Open path fullscreen. Returns Nav for playlist control."""
    cfg = cfg or load_config()
    if not dump and may_be_animated(path) and is_animated(path):
        return play_animated(path, cfg=cfg)

    img = open_image(path)
    if dump:
        from ercomp.image.chrome import cup, render_footer, render_header
        from ercomp.image.gfx import render
        import sys

        geo = geometry()
        head = render_header(geo.cols, name=path.name, size_label=f"{img.width}×{img.height}")
        foot = render_footer(geo.cols, mode="blocks", zoom_label="fit")
        body = render(img, geo)
        sys.stdout.write(f"{cup(1,1)}{head}{cup(max(1,geo.rows),1)}{foot}{body}")
        if not body.endswith("\n"):
            sys.stdout.write("\n")
        return Nav.QUIT
    return view_fullscreen(img, title=path.name, cfg=cfg)
