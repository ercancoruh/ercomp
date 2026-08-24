"""Optional external video backends (mpv) for real FPS / color."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ercomp.mpv_profile import mpv_cli_args
from ercomp.mpv_vendor import mpv_bin
from ercomp.playlist import Nav


def play_with_mpv(
    path: Path,
    *,
    volume: float = 1.0,
    mute: bool = False,
    wait: bool = True,
) -> Nav | None:
    """
    Play in mpv (GPU) with the ercomp profile.

    wait=True blocks until mpv exits. wait=False detaches.
    Returns Nav.QUIT if started, None if mpv unavailable.
    """
    exe = mpv_bin()
    if not exe:
        from ercomp.mpv_vendor import ensure_mpv

        exe = ensure_mpv(force_download=True)
    if not exe:
        return None
    cmd = [exe, *mpv_cli_args(path, volume=volume, mute=mute, wait=wait)]
    try:
        if wait:
            subprocess.run(cmd, check=False)
        else:
            import sys

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
    except OSError:
        return None
    return Nav.QUIT
