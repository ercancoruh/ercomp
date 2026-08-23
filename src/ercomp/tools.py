"""Resolve ffmpeg / ffprobe (pip-bundled imageio-ffmpeg, else system)."""

from __future__ import annotations

import shutil
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def ffmpeg_bin() -> str | None:
    """Prefer pip-bundled binary so `pip install ercomp` is enough."""
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except Exception:
        pass
    return shutil.which("ffmpeg")


@lru_cache(maxsize=1)
def ffprobe_bin() -> str | None:
    found = shutil.which("ffprobe")
    if found:
        return found
    try:
        import imageio_ffmpeg

        getter = getattr(imageio_ffmpeg, "get_ffprobe_exe", None)
        if callable(getter):
            exe = getter()
            if exe and Path(exe).is_file():
                return exe
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        sibling = Path(ffmpeg).parent / "ffprobe"
        if sibling.is_file():
            return str(sibling)
    except Exception:
        pass
    return None


def ffmpeg_source() -> str:
    bundled = None
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    active = ffmpeg_bin()
    if not active:
        return "missing"
    if bundled and active == bundled:
        return f"bundled ({active})"
    return f"system ({active})"
