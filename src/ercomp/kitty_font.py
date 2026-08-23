"""Kitty temporary font size adjust (best-effort)."""

from __future__ import annotations

import os
import shutil
import subprocess


class KittyFontSession:
    """Shrink font while viewing; restore on close. No-op outside Kitty."""

    def __init__(self, delta: float = -2.0) -> None:
        self.delta = delta
        self._active = False
        self._base: float | None = None

    def __enter__(self) -> KittyFontSession:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def start(self) -> None:
        if self.delta == 0 or not os.environ.get("KITTY_WINDOW_ID"):
            return
        if not shutil.which("kitty"):
            return
        try:
            out = subprocess.check_output(
                ["kitty", "@", "get-font-size"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
            )
            self._base = float(out.strip().split()[0])
            new = max(6.0, self._base + self.delta)
            subprocess.check_call(
                ["kitty", "@", "set-font-size", str(new)],
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            self._active = True
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            self._active = False
            self._base = None

    def stop(self) -> None:
        if not self._active or self._base is None:
            return
        try:
            subprocess.check_call(
                ["kitty", "@", "set-font-size", str(self._base)],
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        self._active = False
