"""Spawn media in a separate window; keep the browser session alive."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from ercomp.config import Config, load_config
from ercomp.detect import MediaKind, detect_kind
from ercomp.mpv_vendor import mpv_bin


def _python() -> str:
    return sys.executable


def _view_cmd(path: Path) -> list[str]:
    return [_python(), "-m", "ercomp", "--view", str(path)]


def spawn_terminal_view(path: Path) -> bool:
    """
    Open photo/terminal-video in a new terminal window.
    Returns True if a process was started.
    """
    path = path.resolve()
    cmd = _view_cmd(path)
    title = path.name[:64]

    # Windows Terminal
    wt = shutil.which("wt")
    if wt:
        # new window
        full = [wt, "-w", "new", "--title", title, "-d", str(path.parent), *cmd]
        try:
            subprocess.Popen(
                full,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0),
            )
            return True
        except OSError:
            pass

    if sys.platform == "win32":
        # Fallback: new console window
        try:
            flags = subprocess.CREATE_NEW_CONSOLE  # type: ignore[attr-defined]
            subprocess.Popen(
                cmd,
                cwd=str(path.parent),
                creationflags=flags,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
            )
            return True
        except OSError:
            return False

    # Unix: try gnome-terminal / xterm / kitty
    for launcher in (
        ["kitty", "--title", title, *cmd],
        ["gnome-terminal", "--", *cmd],
        ["xterm", "-T", title, "-e", *cmd],
    ):
        if shutil.which(launcher[0]):
            try:
                subprocess.Popen(
                    launcher,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True
            except OSError:
                continue
    return False


def spawn_mpv(path: Path, *, cfg: Config | None = None) -> bool:
    """Launch mpv in its own GUI window (non-blocking) with ercomp profile."""
    cfg = cfg or load_config()
    exe = mpv_bin()
    if not exe:
        from ercomp.mpv_vendor import ensure_mpv

        exe = ensure_mpv(force_download=True)
    if not exe:
        return False
    from ercomp.mpv_profile import mpv_cli_args

    cmd = [exe, *mpv_cli_args(path, volume=float(cfg.volume), mute=bool(cfg.mute), wait=False)]
    try:
        kwargs: dict = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            kwargs["creationflags"] = (
                getattr(subprocess, "DETACHED_PROCESS", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(cmd, **kwargs)
        return True
    except OSError:
        return False


def open_detached(path: Path, *, cfg: Config | None = None) -> bool:
    """
    Open media without blocking the browser.
    Video → mpv window (fallback: new terminal viewer).
    Image → new terminal viewer window.
    """
    cfg = cfg or load_config()
    kind = detect_kind(path)
    if kind is MediaKind.VIDEO:
        if spawn_mpv(path, cfg=cfg):
            return True
        return spawn_terminal_view(path)
    return spawn_terminal_view(path)
