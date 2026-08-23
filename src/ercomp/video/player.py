"""Fullscreen video playback: audio, seek, playlist nav, screenshot."""

from __future__ import annotations

import signal
import sys
import time
from pathlib import Path

from PIL import Image

from ercomp.audio import AudioPlayer
from ercomp.config import Config, fps_cap_for, load_config
from ercomp.export import save_frame
from ercomp.image.chrome import FOOTER_ROWS, HEADER_ROWS, cup, render_footer, render_header
from ercomp.image.gfx import render
from ercomp.image.term import Protocol, detect_protocol, geometry
from ercomp.input import DISABLE_MOUSE, ENABLE_MOUSE, read_event
from ercomp.kitty_font import KittyFontSession
from ercomp.playlist import Nav
from ercomp.video.decode import open_rgb_pipe, probe


def _write(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


_ENTER_ALT = "\x1b[?1049h"
_LEAVE_ALT = "\x1b[?1049l"
_HIDE_CURSOR = "\x1b[?25l"
_SHOW_CURSOR = "\x1b[?25h"
_CLEAR = "\x1b[2J"
_HOME = "\x1b[H"


def _restore(*, mouse: bool) -> None:
    if mouse:
        _write(DISABLE_MOUSE)
    _write(_SHOW_CURSOR + _LEAVE_ALT)


def _fmt_time(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "--:--"
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def video_info(path: Path) -> str:
    info = probe(path)
    return (
        f"{path.name}\n"
        f"  size     : {info.size_label}\n"
        f"  fps      : {info.fps:.3g}\n"
        f"  duration : {_fmt_time(info.duration)}\n"
        f"  path     : {path.resolve()}\n"
        f"  protocol : {detect_protocol().value}\n"
        f"  audio    : {'on' if AudioPlayer.available() else 'none'}"
    )


def _target_pixels(geo, proto: Protocol) -> tuple[int, int]:
    if proto is Protocol.BLOCKS:
        cols, rows = geo.usable_cells(reserve_rows=HEADER_ROWS + FOOTER_ROWS)
        return cols, rows * 2
    return geo.usable_pixels(reserve_rows=HEADER_ROWS + FOOTER_ROWS)


def play_video(
    path: Path,
    *,
    protocol_name: str | None = None,
    cfg: Config | None = None,
) -> Nav:
    """Play video. Returns Nav for playlist. space pause, arrows seek, m mute, s shot, n/p."""
    cfg = cfg or load_config()
    info = probe(path)
    forced = protocol_name or (None if cfg.protocol == "auto" else cfg.protocol)
    proto = detect_protocol(forced)
    geo = geometry()
    view_w, view_h = _target_pixels(geo, proto)
    cap = fps_cap_for(proto.value, cfg)
    play_fps = min(info.fps, cap) if cap else info.fps
    frame_dt = 1.0 / play_fps
    seek_step = float(cfg.seek_seconds)

    volume = float(cfg.volume)
    mute = bool(cfg.mute)
    audio = AudioPlayer()
    use_mouse = bool(cfg.mouse)

    position = 0.0  # seconds
    paused = False
    last_img: Image.Image | None = None
    status = "video"

    def start_streams(at: float) -> tuple:
        nonlocal position
        position = max(0.0, at)
        if info.duration is not None:
            position = min(position, max(0.0, info.duration - 0.05))
        proc, fw, fh = open_rgb_pipe(
            path,
            max_w=view_w,
            max_h=view_h,
            src_w=info.width,
            src_h=info.height,
            fps_cap=play_fps if play_fps < info.fps - 0.1 else None,
            start=position,
        )
        audio.play(path, start=position, volume=volume, mute=mute)
        return proc, fw, fh, fw * fh * 3

    proc, fw, fh, frame_bytes = start_streams(0.0)
    assert proc.stdout is not None

    if not sys.stdout.isatty():
        raw = proc.stdout.read(frame_bytes)
        proc.kill()
        audio.stop()
        if raw and len(raw) == frame_bytes:
            img = Image.frombytes("RGB", (fw, fh), raw)
            head = render_header(geo.cols, name=path.name, size_label=info.size_label)
            foot = render_footer(geo.cols, protocol=proto.value, zoom_label="video")
            _write(f"{cup(1,1)}{head}\n{render(img, geo, proto, fast=True)}\n{foot}\n")
        return Nav.QUIT

    def draw(img: Image.Image, *, st: str) -> None:
        tlabel = _fmt_time(position)
        total = _fmt_time(info.duration)
        vol = "mute" if mute else f"vol {volume:.1f}"
        size_label = f"{info.size_label}  {tlabel}/{total}  {vol}"
        head = render_header(geo.cols, name=path.name, size_label=size_label)
        foot = render_footer(geo.cols, protocol=proto.value, zoom_label=st)
        body = render(img, geo, proto, fast=True)
        _write(_CLEAR + _HOME)
        _write(f"{cup(1, 1)}{head}{cup(max(1, geo.rows), 1)}{foot}")
        _write(body)
        sys.stdout.flush()

    def restart_at(at: float) -> None:
        nonlocal proc, fw, fh, frame_bytes, position, next_deadline
        try:
            proc.kill()
            proc.wait(timeout=1)
        except Exception:
            pass
        proc, fw, fh, frame_bytes = start_streams(at)
        next_deadline = time.monotonic()

    old_handler = signal.getsignal(signal.SIGINT)

    def _on_sigint(signum, frame):  # noqa: ANN001, ARG001
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _on_sigint)
    fd: int | None = None
    old_term = None
    try:
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_term = termios.tcgetattr(fd)
        tty.setcbreak(fd)
    except Exception:
        fd = None

    font = KittyFontSession(cfg.kitty_font_delta)
    result = Nav.QUIT
    next_deadline = time.monotonic()
    digit_buf = ""

    try:
        font.start()
        _write(_ENTER_ALT + _HIDE_CURSOR + _CLEAR + _HOME)
        if use_mouse:
            _write(ENABLE_MOUSE)

        while True:
            if not paused:
                behind = time.monotonic() - next_deadline
                if behind > frame_dt:
                    skip = min(int(behind / frame_dt), 30)
                    eof = False
                    for _ in range(skip):
                        dumped = proc.stdout.read(frame_bytes)
                        if not dumped or len(dumped) < frame_bytes:
                            eof = True
                            break
                        position += frame_dt
                    if eof:
                        break

                raw = proc.stdout.read(frame_bytes)
                if not raw or len(raw) < frame_bytes:
                    break
                last_img = Image.frombytes("RGB", (fw, fh), raw)
                position += frame_dt
                draw(last_img, st=status)
                next_deadline = max(time.monotonic(), next_deadline + frame_dt)
                deadline = next_deadline
            else:
                deadline = time.monotonic() + 0.1

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 and not paused:
                    break
                if fd is None:
                    if remaining > 0:
                        time.sleep(min(0.05, remaining))
                    if not paused:
                        break
                    continue
                ev = read_event(fd, min(0.05, max(0.0, remaining if remaining > 0 else 0.05)))
                if ev is None:
                    continue

                if ev.kind == "key":
                    key = ev.key
                    if key in ("q", "Q", "\x03", "\x1b"):
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
                        status = "pause" if paused else "video"
                        if paused:
                            audio.stop()
                        else:
                            audio.play(path, start=position, volume=volume, mute=mute)
                            next_deadline = time.monotonic()
                        if last_img is not None:
                            draw(last_img, st=status)
                        break
                    if key == "left":
                        restart_at(position - seek_step)
                        status = "video"
                        break
                    if key == "right":
                        restart_at(position + seek_step)
                        status = "video"
                        break
                    if key in ("m", "M"):
                        mute = not mute
                        audio.set_mute(mute)
                        if last_img is not None:
                            draw(last_img, st=status)
                        break
                    if key == "[":
                        volume = max(0.0, volume - 0.1)
                        audio.set_volume(volume)
                        if last_img is not None:
                            draw(last_img, st=status)
                        break
                    if key == "]":
                        volume = min(2.0, volume + 0.1)
                        audio.set_volume(volume)
                        if last_img is not None:
                            draw(last_img, st=status)
                        break
                    if key in ("s", "S") and last_img is not None:
                        sp = save_frame(last_img, cfg, stem=path.stem)
                        status = f"saved {sp.name}"
                        draw(last_img, st=status)
                        status = "pause" if paused else "video"
                        break
                    if key.isdigit():
                        digit_buf += key
                        break
                    if key in ("g", "G") and digit_buf:
                        try:
                            restart_at(float(digit_buf))
                        except ValueError:
                            pass
                        digit_buf = ""
                        status = "video"
                        break
                    if key == "\r" or key == "\n":
                        if digit_buf:
                            try:
                                restart_at(float(digit_buf))
                            except ValueError:
                                pass
                            digit_buf = ""
                            status = "video"
                        break
                elif ev.kind == "wheel" and last_img is not None:
                    # wheel unused for video zoom; seek instead
                    if ev.key == "zoom_in":
                        restart_at(position + seek_step)
                    else:
                        restart_at(position - seek_step)
                    status = "video"
                    break

        if last_img is not None and fd is not None:
            status = "end"
            audio.stop()
            draw(last_img, st=status)
            while True:
                ev = read_event(fd, 0.5)
                if ev is None:
                    continue
                if ev.kind == "key":
                    if ev.key in ("q", "Q", "\x03", "\x1b"):
                        result = Nav.QUIT
                        break
                    if ev.key in ("n", "N"):
                        result = Nav.NEXT
                        break
                    if ev.key in ("p", "P"):
                        result = Nav.PREV
                        break
    except KeyboardInterrupt:
        result = Nav.QUIT
    finally:
        signal.signal(signal.SIGINT, old_handler)
        audio.stop()
        try:
            proc.kill()
            proc.wait(timeout=2)
        except Exception:
            pass
        if old_term is not None and fd is not None:
            try:
                import termios

                termios.tcsetattr(fd, termios.TCSADRAIN, old_term)
            except Exception:
                pass
        _restore(mouse=use_mouse)
        font.stop()

    return result
