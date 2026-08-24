"""Diagnose environment — ercomp is self-contained after pip install."""

from __future__ import annotations

import os
import sys

from ercomp.image.term import geometry
from ercomp.tools import ffmpeg_bin, ffmpeg_source, ffprobe_bin


def doctor_report() -> str:
    from ercomp.config import load_config, prefer_mpv, video_use_sixel
    from ercomp.image.cap import supports_sixel
    from ercomp.mpv_vendor import mpv_bin, mpv_source

    geo = geometry(probe=True)
    cfg = load_config()
    px = f"{geo.px_width}x{geo.px_height}" if geo.px_width else "?"
    cw, ch = geo.cell_px
    sixel = supports_sixel()
    if prefer_mpv(cfg):
        vmode = "mpv (new window)"
    elif video_use_sixel(cfg):
        vmode = "sixel"
    else:
        vmode = "half-blocks"
    sixel_hint = "yes" if sixel else "no (opt-in only)"
    lines = [
        "mode     : TUI media browser (`ercomp` in cwd)",
        "open     : photos/videos spawn a new window; browser stays open",
        "stills   : truecolor half-blocks (BOX resize)",
        f"video    : {vmode} (backend={cfg.video_backend!r})",
        f"mpv      : {mpv_source()}",
        f"sixel    : {sixel_hint}",
        f"fps_cap  : {cfg.fps_cap}",
        f"budget   : {cfg.cell_budget} cells (terminal-video fallback)",
        f"term     : {geo.cols}x{geo.rows} cells, {px} px, cell {cw}x{ch}",
        f"TERM     : {os.environ.get('TERM', '')}",
        f"WT       : {'yes' if os.environ.get('WT_SESSION') else 'no'}",
        f"tty      : {sys.stdout.isatty()}",
        f"ffmpeg   : {ffmpeg_source()}",
        f"ffprobe  : {ffprobe_bin() or 'via ffmpeg -i'}",
        "bundle   : Pillow + imageio-ffmpeg; mpv auto-download on Windows",
    ]
    if not ffmpeg_bin():
        lines.append("error    : ffmpeg missing — reinstall: pip install --force-reinstall ercomp")
    if not mpv_bin():
        lines.append("hint     : run `ercomp setup-mpv` or `winget install shinchiro.mpv`")
    return "\n".join(lines)


def setup_extras(*, dry_run: bool = False) -> int:
    if dry_run:
        print("would ensure mpv (Windows portable download)")
        return 0
    print("ercomp setup: ensuring ffmpeg (bundled) + mpv…")
    from ercomp.mpv_vendor import install_mpv_for_package

    install_mpv_for_package()
    return 0
