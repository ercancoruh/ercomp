"""Fullscreen video playback: audio, seek, playlist nav, screenshot."""

from __future__ import annotations

import signal
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from ercomp.audio import AudioPlayer
from ercomp.config import Config, fps_cap_for, load_config
from ercomp.export import save_frame
from ercomp.image.chrome import FOOTER_ROWS, HEADER_ROWS, cup, render_footer, render_header
from ercomp.image.gfx import render
from ercomp.image.term import geometry
from ercomp.input import DISABLE_MOUSE, ENABLE_MOUSE, TerminalInput
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
        f"  graphics : truecolor half-blocks\n"
        f"  audio    : {'on' if AudioPlayer.available() else 'none'}"
    )


def _target_pixels(geo) -> tuple[int, int]:
    from ercomp.image.half import budget_cells

    cols, rows = geo.usable_cells(reserve_rows=HEADER_ROWS + FOOTER_ROWS)
    cols, rows = budget_cells(cols, rows)
    w, h = cols, rows * 2
    h -= h % 2
    return max(2, w), max(2, h)


def play_video(
    path: Path,
    *,
    cfg: Config | None = None,
) -> Nav:
    """Play video. Returns Nav for playlist. space pause, arrows seek, m mute, s shot, n/p."""
    cfg = cfg or load_config()
    info = probe(path)
    geo = geometry(probe=True)
    view_w, view_h = _target_pixels(geo)
    cap = fps_cap_for(cfg)
    play_fps = min(info.fps, cap) if cap else info.fps
    frame_dt = 1.0 / max(play_fps, 1.0)
    seek_step = float(cfg.seek_seconds)

    volume = float(cfg.volume)
    mute = bool(cfg.mute)
    audio = AudioPlayer()
    use_mouse = bool(cfg.mouse)

    position = 0.0
    paused = False
    last_img: Image.Image | None = None
    status = "video"
    chrome_dirty = True
    last_header_sec = -1

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
            foot = render_footer(geo.cols, mode="blocks", zoom_label="video")
            _write(f"{cup(1,1)}{head}\n{render(img, geo, fast=True)}\n{foot}\n")
        return Nav.QUIT

    def _chrome(st: str) -> tuple[str, str]:
        tlabel = _fmt_time(position)
        total = _fmt_time(info.duration)
        vol = "mute" if mute else f"vol {volume:.1f}"
        size_label = f"{info.size_label}  {tlabel}/{total}  {vol}"
        head = render_header(geo.cols, name=path.name, size_label=size_label)
        foot = render_footer(geo.cols, mode="blocks", zoom_label=st)
        return head, foot

    def _encode_frame(img: Image.Image) -> str:
        return render(img, geo, fast=True)

    def _present(body: str, *, st: str, full: bool = False) -> None:
        nonlocal chrome_dirty, last_header_sec
        sec = int(position)
        need_chrome = full or chrome_dirty or sec != last_header_sec
        if full or chrome_dirty:
            head, foot = _chrome(st)
            _write(_CLEAR + _HOME)
            _write(f"{cup(1, 1)}{head}{cup(max(1, geo.rows), 1)}{foot}")
            _write(body)
            chrome_dirty = False
            last_header_sec = sec
        elif need_chrome:
            head, foot = _chrome(st)
            _write(f"{cup(1, 1)}{head}{cup(max(1, geo.rows), 1)}{foot}")
            _write(body)
            last_header_sec = sec
        else:
            _write(body)
        sys.stdout.flush()

    def restart_at(at: float) -> None:
        nonlocal proc, fw, fh, frame_bytes, position, next_deadline, chrome_dirty
        try:
            proc.kill()
            proc.wait(timeout=1)
        except Exception:
            pass
        proc, fw, fh, frame_bytes = start_streams(at)
        chrome_dirty = True
        next_deadline = time.monotonic()

    old_handler = signal.getsignal(signal.SIGINT)

    def _on_sigint(signum, frame):  # noqa: ANN001, ARG001
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _on_sigint)
    font = KittyFontSession(cfg.kitty_font_delta)
    result = Nav.QUIT
    next_deadline = time.monotonic()
    digit_buf = ""

    try:
        font.start()
        _write(_ENTER_ALT + _HIDE_CURSOR + _CLEAR + _HOME)
        if use_mouse:
            _write(ENABLE_MOUSE)

        with TerminalInput() as tin, ThreadPoolExecutor(max_workers=1) as pool:
            pending: Future[str] | None = None

            while True:
                if not paused:
                    behind = time.monotonic() - next_deadline
                    if behind > frame_dt:
                        skip = min(int(behind / frame_dt), 60)
                        eof = False
                        for _ in range(skip):
                            dumped = proc.stdout.read(frame_bytes)
                            if not dumped or len(dumped) < frame_bytes:
                                eof = True
                                break
                            position += frame_dt
                        if eof:
                            break
                        next_deadline = time.monotonic()
                        if pending is not None:
                            pending.cancel()
                            pending = None

                    raw = proc.stdout.read(frame_bytes)
                    if not raw or len(raw) < frame_bytes:
                        break
                    last_img = Image.frombytes("RGB", (fw, fh), raw)
                    position += frame_dt

                    pending = pool.submit(_encode_frame, last_img)
                    next_deadline = max(time.monotonic(), next_deadline + frame_dt)
                    deadline = next_deadline
                else:
                    deadline = time.monotonic() + 0.1

                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 and not paused:
                        break
                    ev = tin.read(
                        min(0.04, max(0.0, remaining if remaining > 0 else 0.04))
                    )
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
                            chrome_dirty = True
                            if paused:
                                audio.stop()
                            else:
                                audio.play(
                                    path, start=position, volume=volume, mute=mute
                                )
                                next_deadline = time.monotonic()
                            break
                        if key == "left":
                            if pending is not None:
                                pending.cancel()
                                pending = None
                            restart_at(position - seek_step)
                            status = "video"
                            break
                        if key == "right":
                            if pending is not None:
                                pending.cancel()
                                pending = None
                            restart_at(position + seek_step)
                            status = "video"
                            break
                        if key in ("m", "M"):
                            mute = not mute
                            audio.set_mute(mute)
                            chrome_dirty = True
                            break
                        if key == "[":
                            volume = max(0.0, volume - 0.1)
                            audio.set_volume(volume)
                            chrome_dirty = True
                            break
                        if key == "]":
                            volume = min(2.0, volume + 0.1)
                            audio.set_volume(volume)
                            chrome_dirty = True
                            break
                        if key in ("s", "S") and last_img is not None:
                            sp = save_frame(last_img, cfg, stem=path.stem)
                            status = f"saved {sp.name}"
                            chrome_dirty = True
                            if pending is not None:
                                pending.cancel()
                                pending = None
                            _present(_encode_frame(last_img), st=status, full=True)
                            status = "pause" if paused else "video"
                            break
                        if key.isdigit():
                            digit_buf += key
                            break
                        if key in ("g", "G") and digit_buf:
                            if pending is not None:
                                pending.cancel()
                                pending = None
                            try:
                                restart_at(float(digit_buf))
                            except ValueError:
                                pass
                            digit_buf = ""
                            status = "video"
                            break
                        if key in ("\r", "\n"):
                            if digit_buf:
                                if pending is not None:
                                    pending.cancel()
                                    pending = None
                                try:
                                    restart_at(float(digit_buf))
                                except ValueError:
                                    pass
                                digit_buf = ""
                                status = "video"
                            break
                    elif ev.kind == "wheel":
                        if pending is not None:
                            pending.cancel()
                            pending = None
                        if ev.key == "zoom_in":
                            restart_at(position + seek_step)
                        else:
                            restart_at(position - seek_step)
                        status = "video"
                        break

                if not paused and pending is not None:
                    try:
                        _present(
                            pending.result(timeout=2.0),
                            st=status,
                            full=chrome_dirty,
                        )
                    except Exception:
                        if last_img is not None:
                            _present(
                                _encode_frame(last_img), st=status, full=True
                            )
                    pending = None
                elif paused and last_img is not None and chrome_dirty:
                    _present(_encode_frame(last_img), st=status, full=True)

            if last_img is not None:
                status = "end"
                audio.stop()
                chrome_dirty = True
                if pending is not None:
                    try:
                        _present(pending.result(timeout=0.5), st=status, full=True)
                    except Exception:
                        _present(_encode_frame(last_img), st=status, full=True)
                else:
                    _present(_encode_frame(last_img), st=status, full=True)
                while True:
                    ev = tin.read(0.5)
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
        _restore(mouse=use_mouse)
        font.stop()

    return result
