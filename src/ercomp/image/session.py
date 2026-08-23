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
from ercomp.image.term import Protocol, detect_protocol, geometry
from ercomp.image.zoom import Viewport
from ercomp.input import DISABLE_MOUSE, ENABLE_MOUSE, read_event
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
    proto: Protocol,
    vp: Viewport,
    *,
    name: str,
    size_label: str,
    status: str | None = None,
) -> Image.Image:
    frame = vp.frame(img, geo)
    zoom = status or vp.label()
    head = render_header(geo.cols, name=name, size_label=size_label)
    foot = render_footer(geo.cols, protocol=proto.value, zoom_label=zoom)
    body = render(frame, geo, proto)
    _write(_CLEAR + _HOME)
    _write(f"{cup(1, 1)}{head}{cup(max(1, geo.rows), 1)}{foot}")
    _write(body)
    sys.stdout.flush()
    return frame


def _event_loop(
    img: Image.Image,
    geo,
    proto: Protocol,
    vp: Viewport,
    *,
    name: str,
    cfg: Config,
) -> Nav:
    size_label = f"{img.width}×{img.height}"
    last_frame = _draw(img, geo, proto, vp, name=name, size_label=size_label)
    drag_prev: tuple[int, int] | None = None

    try:
        import termios
        import tty
    except ImportError:
        sys.stdin.readline()
        return Nav.QUIT

    fd = sys.stdin.fileno()
    try:
        old = termios.tcgetattr(fd)
    except termios.error:
        sys.stdin.readline()
        return Nav.QUIT

    try:
        tty.setcbreak(fd)
        while True:
            ev = read_event(fd, timeout=None)
            if ev is None:
                continue
            nav = Nav.NONE
            if ev.kind == "key":
                key = ev.key
                if key in ("q", "Q", "\x03"):
                    return Nav.QUIT
                if key == "\x1b":
                    return Nav.QUIT
                if key in ("n", "N"):
                    return Nav.NEXT
                if key in ("p", "P"):
                    return Nav.PREV
                if key in ("+", "="):
                    vp.zoom_in()
                elif key in ("-", "_"):
                    vp.zoom_out()
                elif key == "0":
                    vp.reset(img)
                elif key == "up":
                    vp.pan(0, -1, img, geo)
                elif key == "down":
                    vp.pan(0, 1, img, geo)
                elif key == "left":
                    vp.pan(-1, 0, img, geo)
                elif key == "right":
                    vp.pan(1, 0, img, geo)
                elif key in ("s", "S"):
                    path = save_frame(last_frame, cfg, stem=Path(name).stem or "ercomp")
                    last_frame = _draw(
                        img,
                        geo,
                        proto,
                        vp,
                        name=name,
                        size_label=size_label,
                        status=f"saved {path.name}",
                    )
                    continue
                else:
                    continue
            elif ev.kind == "wheel":
                if ev.key == "zoom_in":
                    vp.zoom_in()
                else:
                    vp.zoom_out()
            elif ev.kind == "click":
                if ev.pressed and ev.button == 0:
                    drag_prev = (ev.col, ev.row)
                else:
                    drag_prev = None
                continue
            elif ev.kind == "drag" and ev.button == 0:
                if drag_prev is not None:
                    dcol = ev.col - drag_prev[0]
                    drow = ev.row - drag_prev[1]
                    # invert: drag right → pan left (natural)
                    if dcol or drow:
                        vp.pan(-dcol * 0.15, -drow * 0.15, img, geo)
                    drag_prev = (ev.col, ev.row)
                else:
                    drag_prev = (ev.col, ev.row)
            else:
                continue

            geo = geometry()
            last_frame = _draw(img, geo, proto, vp, name=name, size_label=size_label)
            if nav is not Nav.NONE:
                return nav
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)

    return Nav.QUIT


def view_fullscreen(
    img: Image.Image,
    *,
    title: str = "",
    protocol: Protocol | None = None,
    protocol_name: str | None = None,
    cfg: Config | None = None,
) -> Nav:
    """
    Alternate-screen viewer. Returns Nav for playlist control.
    """
    cfg = cfg or load_config()
    forced = protocol_name or (None if cfg.protocol == "auto" else cfg.protocol)
    proto = protocol or detect_protocol(forced)
    geo = geometry()
    name = title or "image"
    vp = Viewport()
    vp.reset(img)
    use_mouse = bool(cfg.mouse)

    if not sys.stdout.isatty():
        frame = vp.frame(img, geo)
        head = render_header(geo.cols, name=name, size_label=f"{img.width}×{img.height}")
        foot = render_footer(geo.cols, protocol=proto.value, zoom_label=vp.label())
        body = render(frame, geo, proto)
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
        result = _event_loop(img, geo, proto, vp, name=name, cfg=cfg)
    except KeyboardInterrupt:
        result = Nav.QUIT
    finally:
        signal.signal(signal.SIGINT, old_handler)
        _restore_terminal(mouse=use_mouse)
        font.stop()

    return result
