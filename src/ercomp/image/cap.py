"""Detect terminal graphics capabilities (sixel, etc.)."""

from __future__ import annotations

import os
import re
import sys
import time

_sixel_cache: bool | None = None


def clear_cap_cache() -> None:
    global _sixel_cache
    _sixel_cache = None


def supports_sixel(*, force: bool | None = None) -> bool:
    """
    True if the terminal likely accepts DEC sixel graphics.

    force: override (True/False) without probing — used by config.
    """
    global _sixel_cache
    if force is not None:
        return bool(force)
    if _sixel_cache is not None:
        return _sixel_cache

    # Explicit env override for CI / debugging
    env = os.environ.get("ERCOMP_SIXEL", "").strip().lower()
    if env in {"1", "true", "yes", "on"}:
        _sixel_cache = True
        return True
    if env in {"0", "false", "no", "off"}:
        _sixel_cache = False
        return False

    if not sys.stdout.isatty():
        _sixel_cache = False
        return False

    # Windows Terminal: honor experimental.sixelSupport in settings.json
    if os.environ.get("WT_SESSION"):
        wt = _wt_sixel_setting()
        if wt is True:
            _sixel_cache = True
            return True
        if wt is False:
            _sixel_cache = False
            return False

    if sys.stdin.isatty():
        probed = _probe_da1_sixel()
        if probed is not None:
            _sixel_cache = probed
            return probed

    _sixel_cache = False
    return False


def _wt_sixel_setting() -> bool | None:
    """Read WT settings for experimental.sixelSupport (True/False/None=unknown)."""
    try:
        from ercomp.font_session import _find_wt_settings, _load_jsonc, _wt_active_profile
    except ImportError:
        return None
    path = _find_wt_settings()
    if path is None:
        return None
    try:
        data = _load_jsonc(path)
    except Exception:
        return None

    def _flag(obj: object) -> bool | None:
        if not isinstance(obj, dict):
            return None
        if "experimental.sixelSupport" in obj:
            return bool(obj["experimental.sixelSupport"])
        return None

    # Profile → defaults → top-level
    profile = _wt_active_profile(data)
    for src in (profile, (data.get("profiles") or {}).get("defaults") if isinstance(data.get("profiles"), dict) else None, data):
        v = _flag(src)
        if v is not None:
            return v
    return None


def _probe_da1_sixel() -> bool | None:
    try:
        sys.stdout.write("\x1b[c")
        sys.stdout.flush()
    except OSError:
        return None

    raw = _read_reply(0.12)
    if not raw:
        return None
    # ESC [ ? 64 ; 1 ; 2 ; 4 ; … c   or similar
    m = re.search(r"\x1b\[\?[\d;]*c", raw)
    if not m:
        return None
    body = m.group(0)
    # Feature 4 = sixel — match as a full numeric token
    return bool(re.search(r"(?:^|[;?])4(?:;|c)", body))


def _read_reply(timeout: float) -> str:
    deadline = time.monotonic() + timeout
    buf = ""
    if sys.platform == "win32":
        import msvcrt

        while time.monotonic() < deadline:
            if msvcrt.kbhit():
                while msvcrt.kbhit():
                    buf += msvcrt.getwch()
                if "c" in buf and "\x1b[" in buf:
                    time.sleep(0.02)
                    while msvcrt.kbhit():
                        buf += msvcrt.getwch()
                    break
            else:
                time.sleep(0.01)
        return buf

    import select

    fd = sys.stdin.fileno()
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if not select.select([fd], [], [], min(0.04, remaining))[0]:
            if buf:
                break
            continue
        try:
            chunk = os.read(fd, 512).decode("latin1", errors="replace")
        except OSError:
            break
        if not chunk:
            break
        buf += chunk
        if "c" in buf:
            break
    return buf
