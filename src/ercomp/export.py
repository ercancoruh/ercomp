"""Save current frame / view to PNG."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from ercomp.config import Config


def screenshot_path(cfg: Config, stem: str = "ercomp") -> Path:
    base = Path(cfg.screenshot_dir).expanduser() if cfg.screenshot_dir else Path.cwd()
    base.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return base / f"{stem}-{ts}.png"


def save_frame(img: Image.Image, cfg: Config, stem: str = "ercomp") -> Path:
    path = screenshot_path(cfg, stem=stem)
    out = img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img
    out.save(path, format="PNG")
    return path
