"""Diagnose environment — ercomp is self-contained after pip install."""

from __future__ import annotations

import os
import sys

from ercomp.image.term import geometry
from ercomp.tools import ffmpeg_bin, ffmpeg_source, ffprobe_bin


def doctor_report() -> str:
    geo = geometry(probe=True)
    px = f"{geo.px_width}x{geo.px_height}" if geo.px_width else "?"
    cw, ch = geo.cell_px
    lines = [
        "graphics : truecolor half-blocks",
        f"term     : {geo.cols}x{geo.rows} cells, {px} px, cell {cw}x{ch}",
        f"TERM     : {os.environ.get('TERM', '')}",
        f"WT       : {'yes' if os.environ.get('WT_SESSION') else 'no'}",
        f"tty      : {sys.stdout.isatty()}",
        f"ffmpeg   : {ffmpeg_source()}",
        f"ffprobe  : {ffprobe_bin() or 'via ffmpeg -i'}",
        "bundle   : Pillow + imageio-ffmpeg (no setup needed)",
    ]
    if not ffmpeg_bin():
        lines.append("error    : ffmpeg missing — reinstall: pip install --force-reinstall ercomp")
    return "\n".join(lines)


def setup_extras(*, dry_run: bool = False) -> int:
    """No-op: everything ships with pip. Kept for backward compatibility."""
    _ = dry_run
    print("ercomp is batteries-included — nothing to install.")
    print("  pip install ercomp   # Pillow + bundled ffmpeg")
    print()
    print(doctor_report())
    return 0 if ffmpeg_bin() else 1
