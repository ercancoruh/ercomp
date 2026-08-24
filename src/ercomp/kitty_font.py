"""Backward-compatible re-export. Prefer ercomp.font_session.FontSession. """

from ercomp.font_session import FontSession, KittyFontSession

__all__ = ["FontSession", "KittyFontSession"]
