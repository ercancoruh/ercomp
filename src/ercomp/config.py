"""User config: ~/.config/ercomp/config.toml"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from pathlib import Path

try:
    import tomllib
except ImportError:  # Python < 3.11
    tomllib = None  # type: ignore[assignment]


@dataclass
class Config:
    fps_cap: float = 24.0
    seek_seconds: float = 5.0
    volume: float = 1.0  # 0..2
    mute: bool = False
    kitty_font_delta: float = 0.0  # Kitty only: relative font size while viewing; 0 = off
    mouse: bool = True
    screenshot_dir: str = ""  # empty → current working directory


_DEFAULT = Config()


def config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "ercomp" / "config.toml"


def load_config() -> Config:
    path = config_path()
    cfg = Config()
    if not path.is_file() or tomllib is None:
        return cfg
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return cfg
    known = {f.name for f in fields(Config)}
    # Legacy keys from older configs
    if "fps_cap_blocks" in data and "fps_cap" not in data:
        data["fps_cap"] = data["fps_cap_blocks"]
    for k, v in data.items():
        if k in known:
            setattr(cfg, k, v)
    return cfg


def save_default_config() -> Path:
    """Write a default config file if missing; return path."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    path.write_text(_default_toml(), encoding="utf-8")
    return path


def _default_toml() -> str:
    c = _DEFAULT
    return f"""# ercomp configuration
# Graphics: truecolor half-blocks only (best color + FPS)
fps_cap = {c.fps_cap}
seek_seconds = {c.seek_seconds}
volume = {c.volume}
mute = {"true" if c.mute else "false"}
kitty_font_delta = {c.kitty_font_delta}
mouse = {"true" if c.mouse else "false"}
screenshot_dir = "{c.screenshot_dir}"
"""


def fps_cap_for(cfg: Config | None = None) -> float | None:
    """Return the playback FPS cap, or None if uncapped."""
    cfg = cfg or load_config()
    return float(cfg.fps_cap) if cfg.fps_cap else None
