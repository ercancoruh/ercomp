"""Header / footer chrome for the fullscreen viewer."""

from __future__ import annotations

_RESET = "\x1b[0m"
_BG = "\x1b[48;2;12;14;18m"
_FG = "\x1b[38;2;220;224;230m"
_MUTED = "\x1b[38;2;120;128;140m"
_ACCENT = "\x1b[38;2;120;190;200m"
_RULE = "\x1b[38;2;42;48;58m"

HEADER_ROWS = 1
FOOTER_ROWS = 1


def _clip(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return "…"
    return text[: width - 1] + "…"


def _paint(cols: int, segments: list[tuple[str, str]]) -> str:
    """Lay out plain-text segments to exactly `cols`, with per-segment colors."""
    texts = [t for _, t in segments]
    colors = [c for c, _ in segments]
    total = sum(map(len, texts))
    if total > cols and texts:
        # Shrink the longest segment
        i = max(range(len(texts)), key=lambda k: len(texts[k]))
        texts[i] = _clip(texts[i], max(0, len(texts[i]) - (total - cols)))
        total = sum(map(len, texts))
    pad = max(0, cols - total)
    if pad and texts:
        texts[-1] = texts[-1] + (" " * pad)
    parts = [_BG]
    for color, text in zip(colors, texts, strict=True):
        parts.append(f"{color}{text}")
    parts.append(_RESET)
    return "".join(parts)


def render_header(cols: int, *, name: str, size_label: str) -> str:
    cols = max(8, cols)
    brand = " ercomp "
    sep = "│"
    right = f" {size_label} "
    mid_w = max(0, cols - len(brand) - len(sep) - len(right))
    mid = _clip(name, mid_w).center(mid_w)
    return _paint(
        cols,
        [(_ACCENT, brand), (_MUTED, sep), (_FG, mid), (_MUTED, right)],
    )


def render_footer(cols: int, *, protocol: str, zoom_label: str = "fit") -> str:
    cols = max(8, cols)
    left = f" {protocol} · {zoom_label} "
    zl = zoom_label
    if zl.startswith("saved"):
        right = " s shot  q quit "
    elif zl in {"video", "pause", "end"}:
        right = " space  ←→ seek  m mute  n/p  s  q "
    elif zl in {"anim"}:
        right = " space  n/p  s  q "
    else:
        right = " +/- zoom  arrows  n/p  s  q "
    if cols < 64:
        if zl in {"video", "pause", "end", "anim"} or zl.startswith("saved"):
            right = " space n/p s q "
        else:
            right = " +/- n/p s q "
    mid_w = max(0, cols - len(left) - len(right))
    return _paint(
        cols,
        [(_MUTED, left), (_RULE, "─" * mid_w), (_MUTED, right)],
    )


def cup(row: int, col: int = 1) -> str:
    return f"\x1b[{row};{col}H"
