"""Thumbnail rendering for the media browser (half-block cards)."""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import Image

from ercomp.browser.scan import Entry, EntryKind
from ercomp.image.half import render_halfblocks_rgb_str
from ercomp.tools import ffmpeg_bin

_RESET = "\x1b[0m"
_BG = "\x1b[48;2;18;22;28m"
_MUTED = "\x1b[38;2;90;100;115m"
_ACCENT = "\x1b[38;2;100;210;200m"
_FOLDER = "\x1b[38;2;200;170;90m"

# Bump when thumb pipeline quality changes (invalidates disk cache)
_THUMB_VER = "v3"


def cache_dir() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    d = base / "ercomp" / "thumbs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cache_key(path: Path, tw: int, th: int) -> str:
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        mtime = 0
    raw = f"{_THUMB_VER}|{path.resolve()}|{mtime}|{tw}x{th}"
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()


def _load_image_rgb(path: Path) -> Image.Image | None:
    try:
        img = Image.open(path)
        img.load()
        # Prefer high-quality decode for stills (EXIF orientation)
        try:
            from PIL import ImageOps

            img = ImageOps.exif_transpose(img)
        except Exception:
            pass
        return img.convert("RGB")
    except Exception:
        return None


def _video_frame_rgb(path: Path, max_edge: int = 320) -> Image.Image | None:
    """Extract a sharp mid-ish frame scaled with lanczos."""
    ffmpeg = ffmpeg_bin()
    if not ffmpeg:
        return None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            out = Path(tmp.name)
        cmd = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            "1",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            f"scale={max_edge}:{max_edge}:force_original_aspect_ratio=decrease:flags=lanczos",
            "-y",
            str(out),
        ]
        proc = subprocess.run(cmd, check=False, capture_output=True, timeout=6)
        if proc.returncode != 0 or not out.is_file() or out.stat().st_size < 32:
            # Retry at t=0 if mid-seek failed
            cmd[cmd.index("-ss") + 1] = "0"
            proc = subprocess.run(cmd, check=False, capture_output=True, timeout=6)
        if proc.returncode != 0 or not out.is_file() or out.stat().st_size < 32:
            out.unlink(missing_ok=True)
            return None
        img = Image.open(out)
        img.load()
        rgb = img.convert("RGB")
        out.unlink(missing_ok=True)
        return rgb
    except Exception:
        try:
            out.unlink(missing_ok=True)
        except Exception:
            pass
        return None


def _first_media_in_dir(directory: Path) -> Path | None:
    from ercomp.playlist import is_media

    try:
        kids = sorted(directory.iterdir(), key=lambda p: p.name.casefold())
    except OSError:
        return None
    for p in kids:
        if is_media(p):
            return p
    return None


def _source_rgb(entry: Entry) -> Image.Image | None:
    if entry.kind is EntryKind.DIR:
        child = _first_media_in_dir(entry.path)
        if child is None:
            return None
        from ercomp.detect import MediaKind, detect_kind

        if detect_kind(child) is MediaKind.VIDEO:
            return _video_frame_rgb(child)
        return _load_image_rgb(child)
    if entry.kind is EntryKind.VIDEO:
        return _video_frame_rgb(entry.path)
    return _load_image_rgb(entry.path)


def _fit(img: Image.Image, tw: int, th_px: int) -> Image.Image:
    """Fit into tw × th_px pixels with Lanczos (sharp thumbs)."""
    tw, th_px = max(2, tw), max(2, th_px)
    th_px -= th_px % 2
    w, h = img.size
    scale = min(tw / w, th_px / h)
    nw, nh = max(1, int(w * scale)), max(2, int(h * scale))
    nh -= nh % 2
    return img.resize((nw, nh), Image.Resampling.LANCZOS)


def _placeholder(cols: int, rows: int, *, kind: EntryKind) -> str:
    rows = max(2, rows)
    cols = max(4, cols)
    if kind is EntryKind.DIR:
        glyph, color = "[/]", _FOLDER
    elif kind is EntryKind.VIDEO:
        glyph, color = "[>]", _ACCENT
    else:
        glyph, color = "[~]", _MUTED

    lines: list[str] = []
    mid = rows // 2
    for r in range(rows):
        if r == mid:
            pad = max(0, (cols - len(glyph)) // 2)
            body = ((" " * pad) + glyph)[:cols].ljust(cols)
            lines.append(f"{_BG}{color}{body}{_RESET}")
        else:
            lines.append(f"{_BG}{' ' * cols}{_RESET}")
    return "\n".join(lines)


def render_thumb_lines(entry: Entry, cols: int, rows: int) -> list[str]:
    """
    Return `rows` terminal lines, each exactly `cols` cells wide (ANSI colored).
    """
    cols = max(4, cols)
    rows = max(2, rows)
    px_h = rows * 2

    key = _cache_key(entry.path, cols, px_h)
    cache_path = cache_dir() / f"{key}.txt"
    if cache_path.is_file():
        try:
            text = cache_path.read_text(encoding="utf-8")
            lines = text.split("\n")
            if len(lines) == rows:
                return [_pad_line(ln, cols) for ln in lines]
        except OSError:
            pass

    rgb = _source_rgb(entry)
    if rgb is None:
        text = _placeholder(cols, rows, kind=entry.kind)
        return [_pad_line(ln, cols) for ln in text.split("\n")]

    fitted = _fit(rgb, cols, px_h)
    canvas = Image.new("RGB", (cols, px_h), (18, 22, 28))
    ox = max(0, (cols - fitted.width) // 2)
    oy = max(0, (px_h - fitted.height) // 2)
    canvas.paste(fitted, (ox, oy))

    art = render_halfblocks_rgb_str(canvas, cols, px_h)
    lines = art.split("\n")
    while len(lines) < rows:
        lines.append(f"{_BG}{' ' * cols}{_RESET}")
    lines = [_pad_line(ln, cols) for ln in lines[:rows]]

    try:
        cache_path.write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass
    return lines


def _pad_line(line: str, cols: int) -> str:
    visible = 0
    i = 0
    while i < len(line):
        if line[i] == "\x1b":
            i += 1
            if i < len(line) and line[i] == "[":
                i += 1
                while i < len(line) and not line[i].isalpha():
                    i += 1
                i += 1
            continue
        visible += 1
        i += 1
    if visible < cols:
        return line + f"{_BG}{' ' * (cols - visible)}{_RESET}"
    return line


@lru_cache(maxsize=512)
def _cached_thumb(path_str: str, mtime_ns: int, cols: int, rows: int, kind: str) -> tuple[str, ...]:
    entry = Entry(path=Path(path_str), kind=EntryKind(kind))
    return tuple(render_thumb_lines(entry, cols, rows))


def thumb_for(entry: Entry, cols: int, rows: int) -> list[str]:
    try:
        mtime = entry.path.stat().st_mtime_ns
    except OSError:
        mtime = 0
    return list(
        _cached_thumb(str(entry.path.resolve()), mtime, cols, rows, entry.kind.value)
    )
