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
    # Absolute font size (pt) while viewing stills on Kitty / Windows Terminal.
    # 1 = smallest; 0 = do not change font. Restored on quit.
    font_size: float = 1.0
    # Video: 0 = leave font alone (recommended). Half-block video needs normal cells for FPS.
    video_font_size: float = 0.0
    mouse: bool = True
    screenshot_dir: str = ""  # empty → current working directory
    # Video graphics in-terminal: blocks (truecolor ▀) | sixel (opt-in, often poor on WT)
    video_graphics: str = "blocks"
    # Soft cap on half-block video cells (safety if the grid is huge).
    cell_budget: int = 10000
    # Sixel palette (only if video_graphics = "sixel")
    sixel_colors: int = 32
    video_max_px: int = 0
    # Where to play video: auto (mpv if installed, else terminal) | terminal | mpv
    video_backend: str = "auto"


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
    # Old delta → jump to minimum size
    if "font_size" not in data and "font_delta" in data:
        try:
            d = float(data["font_delta"])
            data["font_size"] = 0.0 if d == 0 else 1.0
        except (TypeError, ValueError):
            pass
    if "font_size" not in data and "kitty_font_delta" in data:
        try:
            d = float(data["kitty_font_delta"])
            data["font_size"] = 0.0 if d == 0 else 1.0
        except (TypeError, ValueError):
            pass
    # Old configs forced video font shrink — prefer 0 unless explicitly set
    if "video_font_size" not in data:
        data["video_font_size"] = 0.0
    # Old "auto" meant sixel — map to blocks (sixel was a poor default on WT)
    if data.get("video_graphics") == "auto":
        data["video_graphics"] = "blocks"
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
# Stills: truecolor half-blocks (1 pt font). Video: mpv if available, else ▀ blocks.
fps_cap = {c.fps_cap}
seek_seconds = {c.seek_seconds}
volume = {c.volume}
mute = {"true" if c.mute else "false"}
# Font size (pt) while open. Stills default 1; video 0 = leave your font alone.
font_size = {c.font_size}
video_font_size = {c.video_font_size}
# Video playback: auto (prefer mpv) | terminal | mpv
video_backend = "{c.video_backend}"
# In-terminal video graphics: blocks | sixel
video_graphics = "{c.video_graphics}"
cell_budget = {c.cell_budget}
mouse = {"true" if c.mouse else "false"}
screenshot_dir = "{c.screenshot_dir}"
"""


def fps_cap_for(cfg: Config | None = None) -> float | None:
    """Return the playback FPS cap, or None if uncapped."""
    cfg = cfg or load_config()
    return float(cfg.fps_cap) if cfg.fps_cap else None


def video_use_sixel(cfg: Config | None = None) -> bool:
    """Sixel only when explicitly requested (not a good default on Windows Terminal)."""
    cfg = cfg or load_config()
    mode = (cfg.video_graphics or "blocks").strip().lower()
    return mode == "sixel"


def prefer_mpv(cfg: Config | None = None) -> bool:
    cfg = cfg or load_config()
    mode = (cfg.video_backend or "auto").strip().lower()
    if mode in {"terminal", "term", "blocks", "ercomp"}:
        return False
    if mode == "mpv":
        return True
    # auto
    from ercomp.mpv_vendor import mpv_bin

    return mpv_bin() is not None
