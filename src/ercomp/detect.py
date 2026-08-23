"""Media type detection from path / magic bytes / optional ffprobe."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

IMAGE_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".jpe",
        ".jfif",
        ".jfi",
        ".png",
        ".apng",
        ".webp",
        ".gif",
        ".bmp",
        ".dib",
        ".tif",
        ".tiff",
        ".ico",
        ".icns",
        ".ppm",
        ".pgm",
        ".pbm",
        ".pnm",
        ".tga",
        ".avif",
        ".heic",
        ".heif",
        ".hif",
        ".jxl",
        ".jp2",
        ".j2k",
        ".jpf",
        ".jpx",
        ".pcx",
        ".dds",
        ".psd",
        ".xbm",
        ".xpm",
        ".sgi",
        ".rgb",
        ".rgba",
        ".bw",
        ".exr",
        ".hdr",
        ".qoi",
        ".svg",
        ".svgz",
        # camera raw — often via ffmpeg
        ".cr2",
        ".cr3",
        ".nef",
        ".arw",
        ".dng",
        ".orf",
        ".rw2",
        ".raf",
        ".pef",
        ".srw",
    }
)

VIDEO_EXTENSIONS = frozenset(
    {
        ".mp4",
        ".m4v",
        ".mp4v",
        ".mkv",
        ".webm",
        ".avi",
        ".mov",
        ".qt",
        ".wmv",
        ".asf",
        ".flv",
        ".f4v",
        ".mpeg",
        ".mpg",
        ".mpe",
        ".m2v",
        ".m2ts",
        ".mts",
        ".ts",
        ".m3u8",
        ".3gp",
        ".3g2",
        ".ogv",
        ".ogg",
        ".vob",
        ".mxf",
        ".rm",
        ".rmvb",
        ".divx",
        ".xvid",
        ".y4m",
        ".nut",
        ".nsv",
        ".dv",
        ".amv",
        ".wtv",
        ".dvr-ms",
    }
)

# Prefer ffmpeg decode when Pillow is weak / missing codec
FFMPEG_IMAGE_EXTENSIONS = frozenset(
    {
        ".avif",
        ".heic",
        ".heif",
        ".hif",
        ".jxl",
        ".jp2",
        ".j2k",
        ".exr",
        ".hdr",
        ".svg",
        ".svgz",
        ".cr2",
        ".cr3",
        ".nef",
        ".arw",
        ".dng",
        ".orf",
        ".rw2",
        ".raf",
        ".pef",
        ".srw",
        ".psd",
    }
)

_ANIMATED_IMAGE_EXTENSIONS = frozenset({".gif", ".webp", ".apng", ".png"})


class MediaKind(Enum):
    IMAGE = "image"
    VIDEO = "video"
    UNKNOWN = "unknown"


def sniff_mime(path: Path) -> str | None:
    try:
        with path.open("rb") as f:
            head = f.read(32)
    except OSError:
        return None
    if len(head) < 4:
        return None

    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head.startswith(b"BM"):
        return "image/bmp"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"AVI ":
        return "video/avi"
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if head.startswith(b"\x00\x00\x01\x00") or head.startswith(b"\x00\x00\x02\x00"):
        return "image/x-icon"
    if head.startswith(b"\x1aE\xdf\xa3"):
        return "video/x-matroska"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in {b"avif", b"avis"}:
            return "image/avif"
        if brand in {b"heic", b"heif", b"mif1", b"msf1"}:
            return "image/heic"
        if brand in {b"jp2 ", b"jpx "}:
            return "image/jp2"
        # Most other ftyp → video/mp4 family
        return "video/mp4"
    if head.startswith(b"\xff\x0a") or head.startswith(b"\x00\x00\x00\x0cJXL "):
        return "image/jxl"
    if head.startswith(b"qoif"):
        return "image/qoi"
    if head.startswith(b"\x00\x00\x00\x0cjP  "):
        return "image/jp2"
    if head.lstrip().startswith(b"<svg") or head.lstrip().startswith(b"<?xml"):
        if b"svg" in head[:64].lower():
            return "image/svg+xml"
    return None


def _ffprobe_is_video(path: Path) -> bool | None:
    """Return True/False if ffprobe works, None if unavailable."""
    try:
        from ercomp.tools import ffprobe_bin
    except ImportError:
        return None
    ffprobe = ffprobe_bin()
    if not ffprobe:
        return None
    import json
    import subprocess

    try:
        proc = subprocess.run(
            [
                ffprobe,
                "-v",
                "quiet",
                "-print_format",
                "json",
                "-show_streams",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return False
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return False
    for s in data.get("streams") or []:
        if s.get("codec_type") == "video":
            # still image codecs sometimes tagged video — check nb_frames / duration
            codec = (s.get("codec_name") or "").lower()
            if codec in {"mjpeg", "png", "webp", "bmp", "tiff", "gif"}:
                # single-frame or image-in-ffprobe
                nb = s.get("nb_frames")
                if nb in (None, "1", 1, "N/A"):
                    return False
            return True
    return False


def detect_kind(path: Path) -> MediaKind:
    mime = sniff_mime(path)
    if mime:
        if mime.startswith("image/"):
            return MediaKind.IMAGE
        if mime.startswith("video/"):
            return MediaKind.VIDEO

    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS:
        return MediaKind.IMAGE
    if ext in VIDEO_EXTENSIONS:
        return MediaKind.VIDEO

    probed = _ffprobe_is_video(path)
    if probed is True:
        return MediaKind.VIDEO
    if probed is False:
        return MediaKind.IMAGE

    return MediaKind.UNKNOWN


def prefers_ffmpeg_image(path: Path) -> bool:
    return path.suffix.lower() in FFMPEG_IMAGE_EXTENSIONS


def may_be_animated(path: Path) -> bool:
    return path.suffix.lower() in _ANIMATED_IMAGE_EXTENSIONS
