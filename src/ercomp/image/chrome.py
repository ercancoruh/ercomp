"""Modern chrome: header / footer for browser and viewers."""

from __future__ import annotations

_RESET = "\x1b[0m"
_BG = "\x1b[48;2;16;18;24m"
_BG_BAR = "\x1b[48;2;24;28;38m"
_FG = "\x1b[38;2;236;240;246m"
_MUTED = "\x1b[38;2;140;148;162m"
_ACCENT = "\x1b[38;2;100;210;200m"
_ACCENT_DIM = "\x1b[38;2;60;140;135m"
_RULE = "\x1b[38;2;48;54;68m"
_WARN = "\x1b[38;2;240;180;90m"

# Two-row chrome so labels stay readable even with smaller fonts
HEADER_ROWS = 2
FOOTER_ROWS = 2


def _clip(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width == 1:
        return "…"
    return text[: width - 1] + "…"


def _paint(cols: int, segments: list[tuple[str, str]], *, bg: str = _BG_BAR) -> str:
    texts = [t for _, t in segments]
    colors = [c for c, _ in segments]
    total = sum(map(len, texts))
    if total > cols and texts:
        i = max(range(len(texts)), key=lambda k: len(texts[k]))
        texts[i] = _clip(texts[i], max(0, len(texts[i]) - (total - cols)))
        total = sum(map(len, texts))
    pad = max(0, cols - total)
    if pad and texts:
        texts[-1] = texts[-1] + (" " * pad)
    parts = [bg]
    for color, text in zip(colors, texts, strict=True):
        parts.append(f"{color}{text}")
    parts.append(_RESET)
    return "".join(parts)


def _rule_row(cols: int) -> str:
    return f"{_BG}{_ACCENT_DIM}{'▁' * cols}{_RESET}"


def render_header(cols: int, *, name: str, size_label: str) -> str:
    """Two-line header: brand bar + path/title bar."""
    cols = max(12, cols)
    brand = " ERCOMP "
    right = f" {size_label} "
    mid_w = max(0, cols - len(brand) - len(right))
    mid = _clip(name, mid_w).ljust(mid_w)
    line1 = _paint(
        cols,
        [(_ACCENT, brand), (_FG, mid), (_MUTED, right)],
        bg=_BG_BAR,
    )
    line2 = _rule_row(cols)
    return line1 + "\n" + line2


def render_footer(cols: int, *, mode: str = "blocks", zoom_label: str = "fit") -> str:
    """Two-line footer: accent rule + hints."""
    cols = max(12, cols)
    zl = zoom_label
    left = f" {mode} · {zl} "
    if zl.startswith("saved"):
        right = " Backspace/q close "
    elif zl in {"video", "pause", "end"}:
        right = " space  ←→  m  Backspace/q "
    elif zl in {"anim"}:
        right = " space  Backspace/q "
    elif zl in {"browse"}:
        right = " arrows  Enter  Bksp up  q "
    else:
        right = " +/- zoom  arrows  Backspace/q "
    if cols < 56:
        right = " Bksp/q "
    mid_w = max(0, cols - len(left) - len(right))
    line1 = _rule_row(cols)
    line2 = _paint(
        cols,
        [(_MUTED, left), (_RULE, "─" * mid_w), (_MUTED, right)],
        bg=_BG_BAR,
    )
    return line1 + "\n" + line2


def set_window_title(title: str) -> str:
    """OSC 0 — visible in tab/title even when in-cell chrome is tiny."""
    safe = title.replace("\x1b", "").replace("\x07", "")[:120]
    return f"\x1b]0;ercomp — {safe}\x07"


def cup(row: int, col: int = 1) -> str:
    return f"\x1b[{row};{col}H"
