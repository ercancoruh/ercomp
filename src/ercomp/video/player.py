"""Fullscreen video playback: audio, seek, playlist nav, screenshot."""

from __future__ import annotations

import signal
import sys
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from ercomp.audio import AudioPlayer
from ercomp.config import Config, fps_cap_for, load_config, prefer_mpv, video_use_sixel
from ercomp.export import save_frame
from ercomp.font_session import FontSession
from ercomp.image.chrome import FOOTER_ROWS, HEADER_ROWS, cup, render_footer, render_header, set_window_title
from ercomp.image.gfx import render, render_video
from ercomp.image.term import geometry
from ercomp.input import DISABLE_MOUSE, ENABLE_MOUSE, TerminalInput
from ercomp.playlist import Nav
from ercomp.video.decode import open_rgb_pipe, probe
from ercomp.video.external import play_with_mpv


def _write(s: str | bytes) -> None:
    if isinstance(s, bytes):
        sys.stdout.buffer.write(s)
    else:
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
    cfg = load_config()
    if prefer_mpv(cfg):
        gfx = "mpv (external)"
    elif video_use_sixel(cfg):
        gfx = "sixel"
    else:
        gfx = "half-blocks"
    return (
        f"{path.name}\n"
        f"  size     : {info.size_label}\n"
        f"  fps      : {info.fps:.3g}\n"
        f"  duration : {_fmt_time(info.duration)}\n"
        f"  path     : {path.resolve()}\n"
        f"  graphics : {gfx}\n"
        f"  audio    : {'on' if AudioPlayer.available() else 'none'}"
    )


def _target_pixels(geo, *, use_sixel: bool, budget: int, max_px: int) -> tuple[int, int]:
    """Decode size: terminal pixels for sixel, sample grid for budgeted blocks."""
    if use_sixel:
        max_w, max_h = geo.usable_pixels(reserve_rows=HEADER_ROWS + FOOTER_ROWS)
        if max_px and max_px > 0:
            long_edge = max(max_w, max_h)
            if long_edge > max_px:
                s = max_px / long_edge
                max_w = max(2, int(max_w * s))
                max_h = max(2, int(max_h * s))
        # Even height for RGB pipe; sixel encoder will trim to multiple of 6
        h = max_h - (max_h % 2)
        return max(2, max_w), max(2, h)

    import math

    cols, rows = geo.usable_cells(reserve_rows=HEADER_ROWS + FOOTER_ROWS)
    n = max(1, cols * rows)
    budget = max(1000, int(budget))
    if n > budget:
        scale = max(1, int(math.ceil(math.sqrt(n / budget))))
        cols, rows = max(2, cols // scale), max(2, rows // scale)
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

    # Prefer GPU player when available — terminal half-blocks cannot match real video FPS.
    if prefer_mpv(cfg):
        result = play_with_mpv(path, volume=float(cfg.volume), mute=bool(cfg.mute))
        if result is not None:
            return result

    info = probe(path)
    volume = float(cfg.volume)
    mute = bool(cfg.mute)
    audio = AudioPlayer()
    use_mouse = bool(cfg.mouse)
    seek_step = float(cfg.seek_seconds)
    cap = fps_cap_for(cfg)
    play_fps = min(info.fps, cap) if cap else info.fps
    frame_dt = 1.0 / max(play_fps, 1.0)

    want_sixel = video_use_sixel(cfg)
    # Video: do not shrink font by default (1 pt explodes cells → WT can't keep up).
    # Optional video_font_size > 0 still allowed; sixel can opt-in enable flag.
    font = FontSession(0.0, enable_sixel=want_sixel)
    if sys.stdout.isatty():
        font.start()
        from ercomp.image.cap import clear_cap_cache
        from ercomp.image.term import clear_geometry_cache

        clear_cap_cache()
        clear_geometry_cache()

    use_sixel = want_sixel
    geo = geometry(probe=True)
    view_w, view_h = _target_pixels(
        geo,
        use_sixel=use_sixel,
        budget=int(cfg.cell_budget),
        max_px=int(cfg.video_max_px),
    )

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
            foot = render_footer(geo.cols, mode=("sixel" if use_sixel else "blocks"), zoom_label="video")
            _write(f"{cup(1,1)}{head}\n{render(img, geo, fast=True)}\n{foot}\n")
        return Nav.QUIT

    def _chrome(st: str) -> tuple[str, str]:
        tlabel = _fmt_time(position)
        total = _fmt_time(info.duration)
        vol = "mute" if mute else f"vol {volume:.1f}"
        size_label = f"{info.size_label}  {tlabel}/{total}  {vol}"
        head = render_header(geo.cols, name=path.name, size_label=size_label)
        gfx = "sixel" if use_sixel else "blocks"
        foot = render_footer(geo.cols, mode=gfx, zoom_label=st)
        return head, foot

    def _encode_frame(img: Image.Image) -> bytes:
        return render_video(
            img,
            geo,
            use_sixel=use_sixel,
            budget=int(cfg.cell_budget),
            sixel_colors=int(cfg.sixel_colors),
            max_px=int(cfg.video_max_px),
        )

    def _present(body: str | bytes, *, st: str, full: bool = False) -> None:
        nonlocal chrome_dirty, last_header_sec
        sec = int(position)
        need_chrome = full or chrome_dirty or sec != last_header_sec
        if isinstance(body, str):
            body_b = body.encode("utf-8")
        else:
            body_b = body
        if full or chrome_dirty:
            head, foot = _chrome(st)
            foot_row = max(1, geo.rows - FOOTER_ROWS + 1)
            sys.stdout.buffer.write((_CLEAR + _HOME).encode("ascii"))
            sys.stdout.buffer.write(set_window_title(path.name).encode("utf-8"))
            sys.stdout.buffer.write(
                f"{cup(1, 1)}{head}{cup(foot_row, 1)}{foot}".encode("utf-8")
            )
            sys.stdout.buffer.write(body_b)
            chrome_dirty = False
            last_header_sec = sec
        elif need_chrome:
            head, foot = _chrome(st)
            foot_row = max(1, geo.rows - FOOTER_ROWS + 1)
            sys.stdout.buffer.write(
                f"{cup(1, 1)}{head}{cup(foot_row, 1)}{foot}".encode("utf-8")
            )
            sys.stdout.buffer.write(body_b)
            last_header_sec = sec
        else:
            sys.stdout.buffer.write(body_b)
        sys.stdout.buffer.flush()

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
    result = Nav.QUIT
    next_deadline = time.monotonic()
    digit_buf = ""

    try:
        _write(_ENTER_ALT + _HIDE_CURSOR + _CLEAR + _HOME)
        if use_mouse:
            _write(ENABLE_MOUSE)

        with TerminalInput() as tin, ThreadPoolExecutor(max_workers=1) as pool:
            pending: Future[bytes] | None = None

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
                        if ev.key in ("q", "Q", "\x03", "\x1b", "\b", "\x7f") or ev.key == "backspace":
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
