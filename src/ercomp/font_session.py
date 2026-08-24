"""Temporary terminal font shrink for denser half-block grids (best-effort)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

# Smallest size we will set (terminals generally accept ~1pt)
MIN_FONT_SIZE = 1.0


def _wt_settings_paths() -> list[Path]:
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return []
    base = Path(local)
    return [
        base / "Packages" / "Microsoft.WindowsTerminal_8wekyb3d8bbwe" / "LocalState" / "settings.json",
        base / "Packages" / "Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe" / "LocalState" / "settings.json",
        base / "Microsoft" / "Windows Terminal" / "settings.json",
    ]


def _strip_jsonc(text: str) -> str:
    """Remove // and /* */ comments from JSONC (Windows Terminal settings)."""
    out: list[str] = []
    i = 0
    n = len(text)
    in_str = False
    escape = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            i += 2
            while i < n and text[i] not in "\r\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i = min(n, i + 2)
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _load_jsonc(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8-sig")
    return json.loads(_strip_jsonc(raw))


def _find_wt_settings() -> Path | None:
    for p in _wt_settings_paths():
        if p.is_file():
            return p
    return None


def _profile_font_size(profile: dict) -> float | None:
    font = profile.get("font")
    if isinstance(font, dict) and "size" in font:
        try:
            return float(font["size"])
        except (TypeError, ValueError):
            return None
    if "fontSize" in profile:
        try:
            return float(profile["fontSize"])
        except (TypeError, ValueError):
            return None
    return None


def _set_profile_font_size(profile: dict, size: float) -> None:
    font = profile.get("font")
    if isinstance(font, dict):
        font["size"] = size
        profile["font"] = font
        return
    if "fontSize" in profile:
        profile["fontSize"] = size
        return
    profile["font"] = {"size": size}


def _wt_active_profile(data: dict) -> dict | None:
    """Pick the default profile object from settings.json."""
    profiles = data.get("profiles")
    if isinstance(profiles, dict):
        plist = profiles.get("list") or []
        default_guid = data.get("defaultProfile") or profiles.get("default")
    elif isinstance(profiles, list):
        plist = profiles
        default_guid = data.get("defaultProfile")
    else:
        return None

    if not isinstance(plist, list) or not plist:
        return None

    if default_guid:
        for p in plist:
            if isinstance(p, dict) and p.get("guid") == default_guid:
                return p
    for p in plist:
        if isinstance(p, dict) and not p.get("hidden"):
            return p
    return plist[0] if isinstance(plist[0], dict) else None


class FontSession:
    """
    Set terminal font to an absolute size while media is open, then restore.

    - Kitty: `kitty @ set-font-size`
    - Windows Terminal: temporarily patch settings.json (hot-reloads; full file restore)
    - Otherwise: no-op

    enable_sixel: also turn on experimental.sixelSupport in WT for the session.
    """

    def __init__(self, size: float = MIN_FONT_SIZE, *, enable_sixel: bool = False) -> None:
        # Absolute point size while open. 0 = disabled.
        self.size = float(size)
        self.enable_sixel = bool(enable_sixel)
        self._active = False
        self._backend: str | None = None
        self._kitty_base: float | None = None
        self._wt_path: Path | None = None
        self._wt_backup: Path | None = None
        self._atexit_registered = False

    def __enter__(self) -> FontSession:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def start(self) -> None:
        if self._active:
            return
        need_font = self.size > 0
        if not need_font and not self.enable_sixel:
            return
        target = max(MIN_FONT_SIZE, self.size) if need_font else 0.0
        if os.environ.get("KITTY_WINDOW_ID") and need_font and self._start_kitty(target):
            self._register_atexit()
            return
        if os.environ.get("WT_SESSION") and self._start_windows_terminal(
            target if need_font else None
        ):
            self._register_atexit()
            return

    def _register_atexit(self) -> None:
        if self._atexit_registered:
            return
        import atexit

        atexit.register(self.stop)
        self._atexit_registered = True

    def stop(self) -> None:
        if not self._active:
            return
        try:
            if self._backend == "kitty":
                self._stop_kitty()
            elif self._backend == "wt":
                self._stop_windows_terminal()
        finally:
            self._active = False
            self._backend = None

    def _start_kitty(self, target: float) -> bool:
        if not shutil.which("kitty"):
            return False
        try:
            out = subprocess.check_output(
                ["kitty", "@", "get-font-size"],
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
            )
            self._kitty_base = float(out.strip().split()[0])
            if abs(target - self._kitty_base) < 0.05:
                return False
            subprocess.check_call(
                ["kitty", "@", "set-font-size", str(target)],
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            self._backend = "kitty"
            self._active = True
            time.sleep(0.05)
            return True
        except (OSError, subprocess.SubprocessError, ValueError, IndexError):
            self._kitty_base = None
            return False

    def _stop_kitty(self) -> None:
        if self._kitty_base is None:
            return
        try:
            subprocess.check_call(
                ["kitty", "@", "set-font-size", str(self._kitty_base)],
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        self._kitty_base = None

    def _start_windows_terminal(self, target: float | None) -> bool:
        path = _find_wt_settings()
        if path is None:
            return False
        try:
            data = _load_jsonc(path)
        except (OSError, json.JSONDecodeError, UnicodeError):
            return False

        profile = _wt_active_profile(data)
        if profile is None:
            return False

        changed = False
        if target is not None:
            base = _profile_font_size(profile)
            if base is None:
                base = 12.0
            if abs(target - base) >= 0.05:
                _set_profile_font_size(profile, target)
                changed = True

        if self.enable_sixel and not profile.get("experimental.sixelSupport"):
            profile["experimental.sixelSupport"] = True
            changed = True

        if not changed:
            # Still mark active if we only needed sixel and it was already on
            if self.enable_sixel and profile.get("experimental.sixelSupport"):
                self._backend = "wt"
                self._active = True
                return True
            return False

        backup = path.with_name(path.name + ".ercomp-bak")
        try:
            shutil.copy2(path, backup)
        except OSError:
            return False

        try:
            path.write_text(
                json.dumps(data, indent=4, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError:
            try:
                shutil.copy2(backup, path)
                backup.unlink(missing_ok=True)
            except OSError:
                pass
            return False

        self._wt_path = path
        self._wt_backup = backup
        self._backend = "wt"
        self._active = True
        time.sleep(0.35)
        return True

    def _stop_windows_terminal(self) -> None:
        path, backup = self._wt_path, self._wt_backup
        self._wt_path = None
        self._wt_backup = None
        if path is None or backup is None:
            return
        try:
            if backup.is_file():
                shutil.copy2(backup, path)
                backup.unlink(missing_ok=True)
                time.sleep(0.15)
        except OSError:
            pass


# Backward-compatible alias
KittyFontSession = FontSession
