"""Browser grid layout and frame rendering."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ercomp.browser.scan import Entry, EntryKind
from ercomp.browser.thumbs import thumb_for
from ercomp.image.chrome import (
    FOOTER_ROWS,
    HEADER_ROWS,
    _ACCENT,
    _BG_BAR,
    _FG,
    _MUTED,
    _RULE,
    _clip,
    _paint,
    cup,
    render_footer,
)

_RESET = "\x1b[0m"
_BG = "\x1b[48;2;16;18;24m"
_CARD_BG = "\x1b[48;2;22;26;34m"
_SEL = "\x1b[38;2;100;210;200m"
_FG_LOCAL = _FG

_GAP = 2
_LABEL_ROWS = 1


@dataclass(frozen=True)
class GridLayout:
    cols: int
    rows: int
    card_w: int
    card_h: int
    grid_cols: int
    grid_rows: int
    content_rows: int
    origin_row: int
    origin_col: int


def compute_layout(term_cols: int, term_rows: int) -> GridLayout:
    term_cols = max(40, term_cols)
    term_rows = max(14, term_rows)
    content_rows = max(4, term_rows - HEADER_ROWS - FOOTER_ROWS)
    # Larger cards → sharper half-block thumbs
    card_w, card_h = 24, 10
    if term_cols < 70:
        card_w, card_h = 16, 7
    elif term_cols < 100:
        card_w, card_h = 20, 9
    elif term_cols >= 160:
        card_w, card_h = 28, 12

    cell_h = card_h + _LABEL_ROWS
    grid_cols = max(1, (term_cols + _GAP) // (card_w + _GAP))
    grid_rows = max(1, content_rows // cell_h)
    used_w = grid_cols * card_w + (grid_cols - 1) * _GAP
    origin_col = max(1, (term_cols - used_w) // 2 + 1)
    return GridLayout(
        cols=term_cols,
        rows=term_rows,
        card_w=card_w,
        card_h=card_h,
        grid_cols=grid_cols,
        grid_rows=grid_rows,
        content_rows=content_rows,
        origin_row=HEADER_ROWS + 1,
        origin_col=origin_col,
    )


def page_size(layout: GridLayout) -> int:
    return layout.grid_cols * layout.grid_rows


def render_browser_header(
    cols: int,
    *,
    cwd: Path,
    count: int,
    index: int,
    status: str = "",
) -> str:
    brand = " ERCOMP "
    right = f" {index + 1}/{count} " if count else " 0 "
    if status:
        right = f" {status} ·{right}"
    mid_w = max(0, cols - len(brand) - len(right))
    try:
        shown = str(cwd)
    except Exception:
        shown = "."
    mid = _clip(shown, mid_w).ljust(mid_w)
    line1 = _paint(
        cols,
        [(_ACCENT, brand), (_FG, mid), (_MUTED, right)],
        bg=_BG_BAR,
    )
    line2 = f"{_BG}\x1b[38;2;60;140;135m{'▁' * cols}{_RESET}"
    return line1 + "\n" + line2


def render_browser_footer(cols: int) -> str:
    return render_footer(cols, mode="browse", zoom_label="browse")


def _label_line(entry: Entry, width: int, *, selected: bool) -> str:
    if entry.kind is EntryKind.DIR:
        prefix = "▸ "
    elif entry.kind is EntryKind.VIDEO:
        prefix = "▶ "
    else:
        prefix = "  "
    text = _clip(prefix + entry.name, width).ljust(width)
    color = _SEL if selected else _FG_LOCAL
    return f"{_CARD_BG}{color}{text}{_RESET}"


def _frame_card(entry: Entry, layout: GridLayout, *, selected: bool) -> list[str]:
    thumb = thumb_for(entry, layout.card_w, layout.card_h)
    lines = list(thumb)
    lines.append(_label_line(entry, layout.card_w, selected=selected))
    return lines


def render_grid(
    entries: list[Entry],
    layout: GridLayout,
    *,
    page_start: int,
    selected: int,
) -> str:
    n = page_size(layout)
    page = entries[page_start : page_start + n]
    cards = [
        _frame_card(e, layout, selected=(page_start + i == selected))
        for i, e in enumerate(page)
    ]

    out: list[str] = []
    cell_h = layout.card_h + _LABEL_ROWS
    for gr in range(layout.grid_rows):
        row_cards = cards[gr * layout.grid_cols : (gr + 1) * layout.grid_cols]
        if not row_cards:
            break
        for ly in range(cell_h):
            parts: list[str] = []
            for ci, card in enumerate(row_cards):
                if ci:
                    parts.append(f"{_BG}{' ' * _GAP}{_RESET}")
                line = (
                    card[ly]
                    if ly < len(card)
                    else f"{_BG}{' ' * layout.card_w}{_RESET}"
                )
                parts.append(line)
            out.append("".join(parts))

    while len(out) < layout.content_rows:
        out.append(f"{_BG}{' ' * layout.cols}{_RESET}")

    chunks: list[str] = []
    for i, line in enumerate(out[: layout.content_rows]):
        r = layout.origin_row + i
        pad = max(0, layout.origin_col - 1)
        chunks.append(f"{cup(r, 1)}{_BG}{' ' * pad}{_RESET}{line}")
    return "".join(chunks)


def hit_test(
    layout: GridLayout,
    *,
    page_start: int,
    count: int,
    row: int,
    col: int,
) -> int | None:
    if row < layout.origin_row or row >= layout.origin_row + layout.content_rows:
        return None
    cell_h = layout.card_h + _LABEL_ROWS
    local_r = row - layout.origin_row
    gr = local_r // cell_h
    if gr < 0 or gr >= layout.grid_rows:
        return None
    x = col - layout.origin_col
    if x < 0:
        return None
    stride = layout.card_w + _GAP
    gc = x // stride
    if gc < 0 or gc >= layout.grid_cols:
        return None
    if x % stride >= layout.card_w:
        return None
    idx = page_start + gr * layout.grid_cols + gc
    if idx < 0 or idx >= count:
        return None
    return idx
