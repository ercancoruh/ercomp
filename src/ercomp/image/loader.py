"""Open still images via Pillow, with ffmpeg fallback."""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from ercomp.detect import prefers_ffmpeg_image
from ercomp.tools import ffmpeg_bin


class ImageOpenError(Exception):
    """Raised when an image cannot be opened or displayed."""


def _ffmpeg_to_image(path: Path) -> Image.Image:
    ffmpeg = ffmpeg_bin()
    if not ffmpeg:
        raise ImageOpenError(f"cannot open image (need ffmpeg): {path}")
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True)
    except OSError as e:
        raise ImageOpenError(f"ffmpeg failed: {path}: {e}") from e
    if proc.returncode != 0 or not proc.stdout:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise ImageOpenError(err or f"ffmpeg could not decode: {path}")
    try:
        img = Image.open(io.BytesIO(proc.stdout))
        img.load()
        return img.convert("RGBA") if img.mode in ("P", "LA") else img
    except Exception as e:
        raise ImageOpenError(f"ffmpeg produced unreadable image: {path}") from e


def open_image(path: Path) -> Image.Image:
    prefer_ff = prefers_ffmpeg_image(path)
    if prefer_ff and ffmpeg_bin():
        try:
            return _ffmpeg_to_image(path)
        except ImageOpenError:
            pass  # fall through to Pillow

    try:
        img = Image.open(path)
        img.load()
        return img
    except FileNotFoundError as e:
        raise ImageOpenError(f"file not found: {path}") from e
    except UnidentifiedImageError:
        if ffmpeg_bin():
            return _ffmpeg_to_image(path)
        raise ImageOpenError(f"cannot open image: {path}") from None
    except OSError as e:
        if ffmpeg_bin():
            try:
                return _ffmpeg_to_image(path)
            except ImageOpenError:
                pass
        raise ImageOpenError(f"read error: {path}: {e}") from e
