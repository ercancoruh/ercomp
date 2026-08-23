"""Video probe / decode via ffmpeg."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ercomp.image.term import fit_pixels
from ercomp.tools import ffmpeg_bin, ffprobe_bin


class VideoError(Exception):
    """Video cannot be probed or decoded."""


@dataclass(frozen=True)
class VideoInfo:
    path: Path
    width: int
    height: int
    fps: float
    duration: float | None

    @property
    def size_label(self) -> str:
        return f"{self.width}×{self.height}"


def probe(path: Path) -> VideoInfo:
    ffprobe = ffprobe_bin()
    if ffprobe:
        try:
            return _probe_ffprobe(path, ffprobe)
        except VideoError:
            pass
    ffmpeg = ffmpeg_bin()
    if not ffmpeg:
        raise VideoError("ffmpeg not found (pip should ship imageio-ffmpeg)")
    return _probe_ffmpeg(path, ffmpeg)


def _probe_ffprobe(path: Path, ffprobe: str) -> VideoInfo:
    cmd = [
        ffprobe,
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        "-select_streams",
        "v:0",
        str(path),
    ]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
    except OSError as e:
        raise VideoError(f"ffprobe failed: {e}") from e
    if proc.returncode != 0:
        raise VideoError(proc.stderr.strip() or "ffprobe failed")

    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as e:
        raise VideoError("ffprobe returned invalid JSON") from e

    streams = data.get("streams") or []
    if not streams:
        raise VideoError("no video stream")
    s = streams[0]
    width = int(s.get("width") or 0)
    height = int(s.get("height") or 0)
    if width <= 0 or height <= 0:
        raise VideoError("invalid video dimensions")

    fps = _parse_fps(s.get("avg_frame_rate") or s.get("r_frame_rate") or "25/1")
    duration = None
    fmt = data.get("format") or {}
    for src in (fmt.get("duration"), s.get("duration")):
        if src is None:
            continue
        try:
            duration = float(src)
            break
        except (TypeError, ValueError):
            continue

    return VideoInfo(path=path, width=width, height=height, fps=fps, duration=duration)


def _probe_ffmpeg(path: Path, ffmpeg: str) -> VideoInfo:
    """Parse `ffmpeg -i` stderr when ffprobe is unavailable."""
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(path)],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as e:
        raise VideoError(f"ffmpeg failed: {e}") from e
    err = proc.stderr or ""

    # Stream #0:0: Video: h264 (...), 640x360, 24 fps
    m = re.search(
        r"Video:\s*[^\n,]+.*?(\d{2,5})x(\d{2,5}).*?([\d.]+)\s*(?:fps|tbr)",
        err,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        m = re.search(r"(\d{2,5})x(\d{2,5})", err)
        if not m:
            raise VideoError("could not parse video info")
        width, height = int(m.group(1)), int(m.group(2))
        fps = 25.0
    else:
        width, height = int(m.group(1)), int(m.group(2))
        fps = _parse_fps(m.group(3))

    duration = None
    dm = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", err)
    if dm:
        h, mi, s = int(dm.group(1)), int(dm.group(2)), float(dm.group(3))
        duration = h * 3600 + mi * 60 + s

    return VideoInfo(path=path, width=width, height=height, fps=fps, duration=duration)


def _parse_fps(rate: str) -> float:
    try:
        if "/" in rate:
            a, b = rate.split("/", 1)
            num, den = float(a), float(b)
            if den == 0:
                return 25.0
            val = num / den
        else:
            val = float(rate)
        if val <= 0 or val > 120:
            return 25.0
        return val
    except (TypeError, ValueError):
        return 25.0


def open_rgb_pipe(
    path: Path,
    *,
    max_w: int,
    max_h: int,
    src_w: int,
    src_h: int,
    fps_cap: float | None = None,
    start: float = 0.0,
) -> tuple[subprocess.Popen[bytes], int, int]:
    """Start ffmpeg emitting RGB24 frames fitted inside max_w×max_h."""
    ffmpeg = ffmpeg_bin()
    if not ffmpeg:
        raise VideoError("ffmpeg not found (pip should ship imageio-ffmpeg)")

    fw, fh = fit_pixels(src_w, src_h, max(2, max_w), max(2, max_h))
    fw -= fw % 2
    fh -= fh % 2
    fw, fh = max(2, fw), max(2, fh)

    vf_parts = [f"scale={fw}:{fh}:flags=fast_bilinear"]
    if fps_cap and fps_cap > 0:
        vf_parts.append(f"fps={fps_cap:.3f}")

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-hwaccel",
        "auto",
    ]
    if start > 0.05:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += [
        "-i",
        str(path),
        "-vf",
        ",".join(vf_parts),
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-an",
        "-threads",
        "0",
        "-",
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=fw * fh * 3 * 2,
        )
    except OSError as e:
        raise VideoError(f"ffmpeg failed: {e}") from e
    if proc.stdout is None:
        raise VideoError("ffmpeg stdout missing")
    return proc, fw, fh
