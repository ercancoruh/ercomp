"""Fullscreen media browser — cwd, thumbnail grid, open viewers."""

from __future__ import annotations

import signal
import sys
from pathlib import Path

from ercomp.browser.scan import Entry, EntryKind, list_entries
from ercomp.browser.ui import (
    compute_layout,
    hit_test,
    page_size,
    render_browser_footer,
    render_browser_header,
    render_grid,
)
from ercomp.config import Config, load_config
from ercomp.image.chrome import FOOTER_ROWS, HEADER_ROWS, cup, set_window_title
from ercomp.image.term import geometry, geometry_retain
from ercomp.input import DISABLE_MOUSE, ENABLE_MOUSE, TerminalInput
from ercomp.spawn import open_detached

_ENTER_ALT = "\x1b[?1049h"
_LEAVE_ALT = "\x1b[?1049l"
_HIDE_CURSOR = "\x1b[?25l"
_SHOW_CURSOR = "\x1b[?25h"
_CLEAR = "\x1b[2J"
_HOME = "\x1b[H"


def _write(s: str) -> None:
    sys.stdout.write(s)
    sys.stdout.flush()


def _restore(*, mouse: bool) -> None:
    if mouse:
        _write(DISABLE_MOUSE)
    _write(_SHOW_CURSOR + _LEAVE_ALT)


def run_browser(*, start: Path | None = None, cfg: Config | None = None) -> int:
    """
    Main TUI: browse cwd (or start), open media in new windows, return on quit.
    """
    cfg = cfg or load_config()
    use_mouse = bool(cfg.mouse)
    cwd = (start or Path.cwd()).expanduser().resolve()

    if not sys.stdout.isatty():
        entries = list_entries(cwd)
        for e in entries:
            tag = e.kind.value
            print(f"{tag:5} {e.path}")
        return 0 if entries else 1

    selected = 0
    page_start = 0
    entries: list[Entry] = []
    dirty = True
    status_msg = ""

    def refresh_list() -> None:
        nonlocal entries, selected, page_start
        entries = list_entries(cwd)
        if selected >= len(entries):
            selected = max(0, len(entries) - 1)
        page_start = 0
        _ensure_visible()

    def _ensure_visible() -> None:
        nonlocal page_start
        geo = geometry(probe=False)
        layout = compute_layout(geo.cols, geo.rows)
        n = page_size(layout)
        if n <= 0:
            return
        if selected < page_start:
            page_start = selected
        elif selected >= page_start + n:
            page_start = selected - n + 1
        page_start = max(0, page_start)

    def draw(geo) -> None:
        layout = compute_layout(geo.cols, geo.rows)
        _ensure_visible()
        head = render_browser_header(
            geo.cols,
            cwd=cwd,
            count=len(entries),
            index=selected if entries else 0,
            status=status_msg,
        )
        foot = render_browser_footer(geo.cols)
        foot_row = max(1, geo.rows - FOOTER_ROWS + 1)
        _write(set_window_title(str(cwd)))
        _write(_CLEAR + _HOME)
        _write(f"{cup(1, 1)}{head}{cup(foot_row, 1)}{foot}")
        if not entries:
            msg = " no media here — Backspace goes up "
            r = HEADER_ROWS + max(1, (geo.rows - HEADER_ROWS - FOOTER_ROWS) // 2)
            _write(f"{cup(r, 1)}\x1b[38;2;140;148;162m{msg}\x1b[0m")
        else:
            body = render_grid(
                entries, layout, page_start=page_start, selected=selected
            )
            _write(body)
        sys.stdout.flush()

    def go_up() -> None:
        nonlocal cwd, dirty, status_msg
        parent = cwd.parent
        if parent == cwd:
            return
        cwd = parent
        status_msg = ""
        refresh_list()
        dirty = True

    def open_selected() -> None:
        nonlocal cwd, dirty, selected, status_msg
        if not entries:
            return
        e = entries[selected]
        if e.kind is EntryKind.DIR:
            cwd = e.path.resolve()
            status_msg = ""
            refresh_list()
            dirty = True
            return
        # Keep browser alive — open in a new window
        ok = open_detached(e.path, cfg=cfg)
        status_msg = "opened" if ok else "open failed"
        dirty = True

    old_handler = signal.getsignal(signal.SIGINT)

    def _on_sigint(signum, frame):  # noqa: ANN001, ARG001
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _on_sigint)
    refresh_list()
    geo = geometry(probe=True)

    try:
        _write(_ENTER_ALT + _HIDE_CURSOR + _CLEAR + _HOME)
        if use_mouse:
            _write(ENABLE_MOUSE)
        draw(geo)

        with TerminalInput() as tin:
            while True:
                geo2 = geometry_retain(geo)
                if geo2.cols != geo.cols or geo2.rows != geo.rows:
                    geo = geo2
                    dirty = True
                if dirty:
                    draw(geo)
                    dirty = False

                ev = tin.read(0.2)
                if ev is None:
                    continue

                layout = compute_layout(geo.cols, geo.rows)
                n = page_size(layout)
                cols = layout.grid_cols

                if ev.kind == "key":
                    key = ev.key
                    if key in ("q", "Q", "\x03"):
                        return 0
                    if key == "\x1b":
                        if cwd.parent != cwd:
                            go_up()
                        else:
                            return 0
                        continue
                    if key in ("\x7f", "\b", "h", "H") or key == "backspace":
                        go_up()
                        continue
                    if key in ("\r", "\n", "o", "O"):
                        open_selected()
                        continue
                    if key == "left":
                        if selected > 0:
                            selected -= 1
                            dirty = True
                    elif key == "right":
                        if selected < len(entries) - 1:
                            selected += 1
                            dirty = True
                    elif key == "up":
                        if selected >= cols:
                            selected -= cols
                            dirty = True
                    elif key == "down":
                        if selected + cols < len(entries):
                            selected += cols
                            dirty = True
                        elif selected < len(entries) - 1:
                            selected = len(entries) - 1
                            dirty = True
                    elif key in ("n", "N", "pagedown"):
                        selected = min(len(entries) - 1, selected + n)
                        dirty = True
                    elif key in ("p", "P", "pageup"):
                        selected = max(0, selected - n)
                        dirty = True
                    elif key == "g":
                        selected = 0
                        dirty = True
                    elif key == "G":
                        selected = max(0, len(entries) - 1)
                        dirty = True
                    elif key in ("r", "R"):
                        refresh_list()
                        dirty = True

                elif ev.kind == "click" and ev.pressed:
                    hit = hit_test(
                        layout,
                        page_start=page_start,
                        count=len(entries),
                        row=ev.row,
                        col=ev.col,
                    )
                    if hit is not None:
                        if hit == selected:
                            open_selected()
                        else:
                            selected = hit
                            dirty = True
                elif ev.kind == "wheel":
                    if ev.key == "zoom_in" or ev.dy < 0:
                        selected = max(0, selected - cols)
                    else:
                        selected = min(len(entries) - 1, selected + cols)
                    dirty = True

    except KeyboardInterrupt:
        return 0
    finally:
        signal.signal(signal.SIGINT, old_handler)
        _restore(mouse=use_mouse)

    return 0
