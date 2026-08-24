"""Fullscreen alternate-screen image session with zoom/pan/mouse."""

from __future__ import annotations

import signal
import sys
from typing import TYPE_CHECKING

from pathlib import Path

from ercomp.config import Config, load_config
from ercomp.export import save_frame
from ercomp.image.chrome import cup, render_footer, render_header
from ercomp.image.gfx import render
from ercomp.image.term import geometry, geometry_retain
from ercomp.image.zoom import Viewport
from ercomp.input import DISABLE_MOUSE, ENABLE_MOUSE, Event, TerminalInput
from ercomp.kitty_font import KittyFontSession
from ercomp.playlist import Nav

if TYPE_CHECKING:
    from PIL import Image

_ENTER_ALT = "\x1b[?1049h"
_LEAVE_ALT = "\x1b[?1049l"
_HIDE_CURSOR = "\x1b[?25l"
_SHOW_CURSOR = "\x1b[?25h"
_CLEAR = "\x1b[2J"
_HOME = "\x1b[H"

_ZOOM_KEYS = {"+", "=", "-", "_", "0", "up", "down", "left", "right"}


def _write(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def _restore_terminal(*, mouse: bool) -> None:
    if mouse:
        _write(DISABLE_MOUSE)
    _write(_SHOW_CURSOR + _LEAVE_ALT)


def _draw(
    img: Image.Image,
    geo,
    vp: Viewport,
    *,
    name: str,
    size_label: str,
    status: str | None = None,
    interactive: bool = False,
) -> Image.Image:
    frame = vp.frame(img, geo)
    zoom = status or vp.label()
    head = render_header(geo.cols, name=name, size_label=size_label)
    foot = render_footer(geo.cols, mode="blocks", zoom_label=zoom)
    # Only throttle quality during interactive zoom/pan — never for the initial still
    fast = interactive
    body = render(frame, geo, fast=fast)
    _write(_CLEAR + _HOME)
    _write(f"{cup(1, 1)}{head}{cup(max(1, geo.rows), 1)}{foot}")
    _write(body)
    sys.stdout.flush()
    return frame


def _apply_view_key(key: str, vp: Viewport, img: Image.Image, geo) -> bool:
    """Apply zoom/pan key. Returns True if viewport changed."""
    if key in ("+", "="):
        vp.zoom_in()
        return True
    if key in ("-", "_"):
        vp.zoom_out()
        return True
    if key == "0":
        vp.reset(img)
        return True
    if key == "up":
        vp.pan(0, -1, img, geo)
        return True
    if key == "down":
        vp.pan(0, 1, img, geo)
        return True
    if key == "left":
        vp.pan(-1, 0, img, geo)
        return True
    if key == "right":
        vp.pan(1, 0, img, geo)
        return True
    return False


def _coalesce_view_events(
    tin: TerminalInput, first: Event, vp: Viewport, img: Image.Image, geo
) -> Event | None:
    """
    Drain queued zoom/pan/wheel events so holding +/- redraws once.
    Returns a non-view event that interrupted coalescing, if any.
    """
    ev: Event | None = first
    while ev is not None:
        if ev.kind == "key" and ev.key in _ZOOM_KEYS:
            _apply_view_key(ev.key, vp, img, geo)
        elif ev.kind == "wheel":
            if ev.key == "zoom_in":
                vp.zoom_in()
            else:
                vp.zoom_out()
        elif ev.kind == "drag" and ev.button == 0:
            return ev
        elif ev.kind == "key":
            return ev
        else:
            return ev
        ev = tin.read(0)
    return None


def _event_loop(
    img: Image.Image,
    geo,
    vp: Viewport,
    *,
    name: str,
    cfg: Config,
) -> Nav:
    size_label = f"{img.width}×{img.height}"
    last_frame = _draw(
        img, geo, vp, name=name, size_label=size_label, interactive=False
    )
    drag_prev: tuple[int, int] | None = None

    with TerminalInput() as tin:
        while True:
            ev = tin.read(timeout=None)
            if ev is None:
                continue

            # Coalesce rapid zoom/pan/wheel into one redraw
            if (ev.kind == "key" and ev.key in _ZOOM_KEYS) or ev.kind == "wheel":
                pending = _coalesce_view_events(tin, ev, vp, img, geo)
                geo = geometry_retain(geo)
                last_frame = _draw(
                    img,
                    geo,
                    vp,
                    name=name,
                    size_label=size_label,
                    interactive=True,
                )
                if pending is None:
                    continue
                ev = pending

            if ev.kind == "key":
                key = ev.key
                if key in ("q", "Q", "\x03", "\x1b"):
                    return Nav.QUIT
                if key in ("n", "N"):
                    return Nav.NEXT
                if key in ("p", "P"):
                    return Nav.PREV
                if key in ("s", "S"):
                    path = save_frame(last_frame, cfg, stem=Path(name).stem or "ercomp")
                    last_frame = _draw(
                        img,
                        geo,
                        vp,
                        name=name,
                        size_label=size_label,
                        status=f"saved {path.name}",
                        interactive=True,
                    )
                    continue
                continue

            if ev.kind == "click":
                if ev.pressed and ev.button == 0:
                    drag_prev = (ev.col, ev.row)
                else:
                    drag_prev = None
                continue

            if ev.kind == "drag" and ev.button == 0:
                if drag_prev is not None:
                    dcol = ev.col - drag_prev[0]
                    drow = ev.row - drag_prev[1]
                    if dcol or drow:
                        vp.pan(-dcol * 0.15, -drow * 0.15, img, geo)
                    drag_prev = (ev.col, ev.row)
                else:
                    drag_prev = (ev.col, ev.row)
                # Coalesce further drag events
                while True:
                    more = tin.read(0)
                    if more is None or more.kind != "drag":
                        break
                    if drag_prev is not None:
                        dcol = more.col - drag_prev[0]
                        drow = more.row - drag_prev[1]
                        if dcol or drow:
                            vp.pan(-dcol * 0.15, -drow * 0.15, img, geo)
                        drag_prev = (more.col, more.row)
                geo = geometry_retain(geo)
                last_frame = _draw(
                    img,
                    geo,
                    vp,
                    name=name,
                    size_label=size_label,
                    interactive=True,
                )
                continue

    return Nav.QUIT


def view_fullscreen(
    img: Image.Image,
    *,
    title: str = "",
    cfg: Config | None = None,
) -> Nav:
    """
    Alternate-screen viewer. Returns Nav for playlist control.
    """
    cfg = cfg or load_config()
    geo = geometry(probe=True)
    name = title or "image"
    vp = Viewport()
    vp.reset(img)
    use_mouse = bool(cfg.mouse)

    if not sys.stdout.isatty():
        frame = vp.frame(img, geo)
        head = render_header(geo.cols, name=name, size_label=f"{img.width}×{img.height}")
        foot = render_footer(geo.cols, mode="blocks", zoom_label=vp.label())
        body = render(frame, geo)
        _write(f"{cup(1, 1)}{head}\n{body}\n{foot}\n")
        return Nav.QUIT

    old_handler = signal.getsignal(signal.SIGINT)

    def _on_sigint(signum, frame):  # noqa: ANN001, ARG001
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _on_sigint)
    font = KittyFontSession(cfg.kitty_font_delta)
    result = Nav.QUIT
    try:
        font.start()
        _write(_ENTER_ALT + _HIDE_CURSOR + _CLEAR + _HOME)
        if use_mouse:
            _write(ENABLE_MOUSE)
        result = _event_loop(img, geo, vp, name=name, cfg=cfg)
    except KeyboardInterrupt:
        result = Nav.QUIT
    finally:
        signal.signal(signal.SIGINT, old_handler)
        _restore_terminal(mouse=use_mouse)
        font.stop()

    return result
