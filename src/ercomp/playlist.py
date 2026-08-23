"""Playlist / directory browsing."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from ercomp.detect import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, detect_kind, MediaKind


class Nav(Enum):
    QUIT = "quit"
    NEXT = "next"
    PREV = "prev"
    # stay / redraw
    NONE = "none"


def is_media(path: Path) -> bool:
    if not path.is_file():
        return False
    ext = path.suffix.lower()
    if ext in IMAGE_EXTENSIONS or ext in VIDEO_EXTENSIONS:
        return True
    kind = detect_kind(path)
    return kind in (MediaKind.IMAGE, MediaKind.VIDEO)


def build_playlist(path: Path) -> list[Path]:
    """
    File → playlist of sibling media in the same directory (sorted),
    starting context preserved by index lookup.
    Directory → all media files inside (non-recursive), sorted.
    """
    path = path.expanduser().resolve()
    if path.is_dir():
        items = sorted(p for p in path.iterdir() if is_media(p))
        return items
    if path.is_file():
        parent = path.parent
        siblings = sorted(p for p in parent.iterdir() if is_media(p))
        if path in siblings:
            return siblings
        return [path]
    return []


def index_of(playlist: list[Path], path: Path) -> int:
    path = path.resolve()
    for i, p in enumerate(playlist):
        if p.resolve() == path:
            return i
    return 0
