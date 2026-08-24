"""Locate or download a portable mpv binary (Windows / Linux)."""

from __future__ import annotations

import os
import platform
import shutil
import sys
import urllib.request
import zipfile
from functools import lru_cache
from pathlib import Path

# Portable ZIP builds (no 7z needed). Updated via GitHub latest redirect.
_WIN_ZIP = (
    "https://github.com/JJenkx/mpv-atmos-patched/releases/latest/download/"
    "mpv-atmos-stock-windows-x86_64.zip"
)


def _cache_root() -> Path:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    d = base / "ercomp" / "mpv"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _bundled_dir() -> Path:
    """site-packages/ercomp/_mpv — populated at install / first ensure."""
    return Path(__file__).resolve().parent / "_mpv"


def _find_exe(root: Path) -> Path | None:
    names = ("mpv.exe", "mpv") if sys.platform == "win32" else ("mpv",)
    for name in names:
        direct = root / name
        if direct.is_file():
            return direct
    # Nested extract
    for name in names:
        for p in root.rglob(name):
            if p.is_file():
                return p
    return None


def _system_mpv() -> str | None:
    return shutil.which("mpv")


def _download_windows(dest: Path) -> Path | None:
    dest.mkdir(parents=True, exist_ok=True)
    zip_path = dest / "mpv-download.zip"
    try:
        req = urllib.request.Request(_WIN_ZIP, headers={"User-Agent": "ercomp"})
        with urllib.request.urlopen(req, timeout=120) as resp, zip_path.open("wb") as out:
            shutil.copyfileobj(resp, out)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(dest)
        zip_path.unlink(missing_ok=True)
        return _find_exe(dest)
    except Exception:
        zip_path.unlink(missing_ok=True)
        return None


def ensure_mpv(*, force_download: bool = False) -> str | None:
    """
    Return path to mpv executable.

    Order: system PATH → package _mpv/ → user cache → download (Windows).
    """
    if not force_download:
        sys_mpv = _system_mpv()
        if sys_mpv:
            return sys_mpv
        for root in (_bundled_dir(), _cache_root()):
            found = _find_exe(root)
            if found:
                return str(found)

    if sys.platform == "win32" and platform.machine().lower() in {
        "amd64",
        "x86_64",
        "x64",
    }:
        # Prefer install into package dir when writable, else cache
        for root in (_bundled_dir(), _cache_root()):
            try:
                root.mkdir(parents=True, exist_ok=True)
                test = root / ".write_test"
                test.write_text("ok", encoding="utf-8")
                test.unlink(missing_ok=True)
            except OSError:
                continue
            found = _download_windows(root)
            if found:
                return str(found)
    return _system_mpv()


@lru_cache(maxsize=1)
def mpv_bin() -> str | None:
    return ensure_mpv(force_download=False)


def mpv_source() -> str:
    exe = mpv_bin()
    if not exe:
        return "missing"
    p = Path(exe)
    try:
        if _bundled_dir() in p.parents or p.parent == _bundled_dir():
            return f"bundled ({exe})"
        if _cache_root() in p.parents:
            return f"cached ({exe})"
    except Exception:
        pass
    return f"system ({exe})"


def install_mpv_for_package() -> None:
    """Called from setup / `ercomp setup-mpv` — download into package _mpv on Windows."""
    if sys.platform != "win32":
        print("mpv auto-bundle is Windows-only; install mpv from your package manager.")
        return
    path = ensure_mpv(force_download=True)
    if path:
        print(f"mpv ready: {path}")
    else:
        print("mpv download failed — install via: winget install shinchiro.mpv")
