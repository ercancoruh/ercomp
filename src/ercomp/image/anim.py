"""Animated GIF / WebP / APNG playback."""

from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

from PIL import Image, ImageSequence

from ercomp.config import Config, load_config, video_use_sixel
from ercomp.export import save_frame
from ercomp.image.chrome import FOOTER_ROWS, cup, render_footer, render_header
from ercomp.image.gfx import render_video
from ercomp.image.loader import ImageOpenError
from ercomp.image.term import geometry
from ercomp.font_session import FontSession
from ercomp.image.zoom import Viewport
from ercomp.input import DISABLE_MOUSE, ENABLE_MOUSE, TerminalInput
from ercomp.playlist import Nav


def _write(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


_ENTER_ALT = "\x1b[?1049h"
_LEAVE_ALT = "\x1b[?1049l"
_HIDE_CURSOR = "\x1b[?25l"
_SHOW_CURSOR = "\x1b[?25h"
_CLEAR = "\x1b[2J"
_HOME = "\x1b[H"


def is_animated(path: Path) -> bool:
    try:
        img = Image.open(path)
    except OSError:
        return False
    return bool(getattr(img, "is_animated", False) and getattr(img, "n_frames", 1) > 1)


def play_animated(
    path: Path,
    *,
    cfg: Config | None = None,
) -> Nav:
    """Loop animated image frames. space=pause, n/p playlist, s screenshot, q=quit."""
    cfg = cfg or load_config()
    try:
        src = Image.open(path)
        src.load()
    except OSError as e:
        raise ImageOpenError(f"cannot open image: {path}") from e

    if not (getattr(src, "is_animated", False) and src.n_frames > 1):
        raise ImageOpenError(f"not an animated image: {path}")

    frames: list[tuple[Image.Image, float]] = []
    for frame in ImageSequence.Iterator(src):
        ms = frame.info.get("duration", 100) or 100
        delay = max(0.02, ms / 1000.0)
        frames.append((frame.copy().convert("RGBA"), delay))

    use_mouse = bool(cfg.mouse)
    font = FontSession(0.0)

    use_sixel = video_use_sixel(cfg)

    def draw(img: Image.Image, geo, vp: Viewport, *, status: str) -> Image.Image:
        fitted = vp.frame(img, geo)
        head = render_header(
            geo.cols,
            name=path.name,
            size_label=f"{src.width}×{src.height}  {src.n_frames}f",
        )
        mode = "sixel" if use_sixel else "anim"
        foot = render_footer(geo.cols, mode=mode, zoom_label=status)
        body = render_video(
            fitted,
            geo,
            use_sixel=use_sixel,
            budget=int(cfg.cell_budget),
            sixel_colors=int(cfg.sixel_colors),
            max_px=int(cfg.video_max_px),
        )
        foot_row = max(1, geo.rows - FOOTER_ROWS + 1)
        _write(_CLEAR + _HOME)
        _write(f"{cup(1,1)}{head}{cup(foot_row,1)}{foot}")
        if isinstance(body, bytes):
            sys.stdout.buffer.write(body)
        else:
            sys.stdout.write(body)
        sys.stdout.flush()
        return fitted

    if not sys.stdout.isatty():
        geo = geometry(probe=True)
        vp = Viewport()
        vp.reset(frames[0][0])
        draw(frames[0][0], geo, vp, status="anim")
        return Nav.QUIT

    old_handler = signal.getsignal(signal.SIGINT)

    def _on_sigint(signum, frame):  # noqa: ANN001, ARG001
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _on_sigint)
    paused = False
    idx = 0
    result = Nav.QUIT
    last_fitted = frames[0][0]

    try:
        font.start()
        geo = geometry(probe=True)
        vp = Viewport()
        vp.reset(frames[0][0])
        _write(_ENTER_ALT + _HIDE_CURSOR + _CLEAR + _HOME)
        if use_mouse:
            _write(ENABLE_MOUSE)
        with TerminalInput() as tin:
            while True:
                img, delay = frames[idx]
                last_fitted = draw(img, geo, vp, status="pause" if paused else "anim")
                deadline = time.monotonic() + (0.1 if paused else delay)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 and not paused:
                        break
                    ev = tin.read(min(0.05, max(0.0, remaining if remaining > 0 else 0.05)))
                    if ev is None:
                        continue
                    if ev.kind != "key":
                        continue
                    key = ev.key
                    if key in ("q", "Q", "\x03", "\x1b", "\b", "\x7f") or key == "backspace":
                        result = Nav.QUIT
                        return result
                    if key in ("n", "N"):
                        result = Nav.NEXT
                        return result
                    if key in ("p", "P"):
                        result = Nav.PREV
                        return result
                    if key == " ":
                        paused = not paused
                        break
                    if key in ("s", "S"):
                        sp = save_frame(last_fitted, cfg, stem=path.stem)
                        draw(img, geo, vp, status=f"saved {sp.name}")
                        break
                if not paused:
                    idx = (idx + 1) % len(frames)
    except KeyboardInterrupt:
        result = Nav.QUIT
    finally:
        signal.signal(signal.SIGINT, old_handler)
        if use_mouse:
            _write(DISABLE_MOUSE)
        _write(_SHOW_CURSOR + _LEAVE_ALT)
        font.stop()

    return result
