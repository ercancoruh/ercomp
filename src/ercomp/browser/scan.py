"""Directory scan: folders-with-media + media files only."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ercomp.detect import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, detect_kind, MediaKind
from ercomp.playlist import dir_has_media, is_media


class EntryKind(Enum):
    DIR = "dir"
    IMAGE = "image"
    VIDEO = "video"


@dataclass(frozen=True)
class Entry:
    path: Path
    kind: EntryKind

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def label(self) -> str:
        if self.kind is EntryKind.DIR:
            return self.name
        return self.name


def _file_kind(path: Path) -> EntryKind:
    kind = detect_kind(path)
    if kind is MediaKind.VIDEO:
        return EntryKind.VIDEO
    # Prefer extension for speed when sniff is ambiguous
    ext = path.suffix.lower()
    if ext in VIDEO_EXTENSIONS:
        return EntryKind.VIDEO
    if ext in IMAGE_EXTENSIONS:
        return EntryKind.IMAGE
    return EntryKind.IMAGE


def list_entries(directory: Path) -> list[Entry]:
    """
    Non-recursive listing for the browser.

    - Subdirectories that directly contain media
    - Media files in this directory
    Sorted: dirs first (by name), then files (by name). Case-insensitive.
    """
    directory = directory.expanduser().resolve()
    dirs: list[Entry] = []
    files: list[Entry] = []
    try:
        children = list(directory.iterdir())
    except OSError:
        return []

    for p in children:
        try:
            if p.is_dir():
                if dir_has_media(p):
                    dirs.append(Entry(path=p, kind=EntryKind.DIR))
            elif is_media(p):
                files.append(Entry(path=p, kind=_file_kind(p)))
        except OSError:
            continue

    key = lambda e: e.name.casefold()
    dirs.sort(key=key)
    files.sort(key=key)
    return dirs + files
