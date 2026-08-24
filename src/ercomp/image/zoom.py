"""Zoom / pan viewport over a source image."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image

from ercomp.image.chrome import FOOTER_ROWS, HEADER_ROWS
from ercomp.image.term import TermGeometry, fit_pixels

_RESERVE = HEADER_ROWS + FOOTER_ROWS
_ZOOM_MIN = 1.0
_ZOOM_MAX = 32.0
_ZOOM_STEP = 1.25
_PAN_FRAC = 0.20


def _view_samples(geo: TermGeometry) -> tuple[int, int]:
    """
    Half-block sample grid for the content area (matches gfx.render_blocks).

    One cell = 1×2 samples (▀). Must not use pixel cell metrics — those drift
    after font shrink and made zoomed frames undersized.
    """
    cols, rows = geo.usable_cells(reserve_rows=_RESERVE)
    return max(2, cols), max(2, rows * 2)


@dataclass
class Viewport:
    """Zoom >= 1; pan is the crop center in source-image pixels."""

    zoom: float = 1.0
    cx: float = 0.0
    cy: float = 0.0

    def reset(self, img: Image.Image) -> None:
        self.zoom = 1.0
        self.cx = img.width / 2
        self.cy = img.height / 2

    def zoom_in(self) -> None:
        self.zoom = min(_ZOOM_MAX, self.zoom * _ZOOM_STEP)

    def zoom_out(self) -> None:
        self.zoom = max(_ZOOM_MIN, self.zoom / _ZOOM_STEP)

    def pan(self, dx: float, dy: float, img: Image.Image, geo: TermGeometry) -> None:
        if self.zoom <= 1.0 + 1e-6:
            return
        crop_w, crop_h = self._crop_size(img, geo)
        self.cx += dx * crop_w * _PAN_FRAC
        self.cy += dy * crop_h * _PAN_FRAC
        self._clamp(img, crop_w, crop_h)

    def _crop_size(self, img: Image.Image, geo: TermGeometry) -> tuple[float, float]:
        view_w, view_h = _view_samples(geo)
        fit = min(view_w / img.width, view_h / img.height)
        scale = fit * self.zoom
        crop_w = min(float(img.width), view_w / max(scale, 1e-9))
        crop_h = min(float(img.height), view_h / max(scale, 1e-9))
        return crop_w, crop_h

    def _clamp(self, img: Image.Image, crop_w: float, crop_h: float) -> None:
        half_w, half_h = crop_w / 2, crop_h / 2
        self.cx = min(max(self.cx, half_w), max(half_w, img.width - half_w))
        self.cy = min(max(self.cy, half_h), max(half_h, img.height - half_h))

    def frame(self, img: Image.Image, geo: TermGeometry) -> Image.Image:
        """
        Crop visible region from source, scale once to the half-block sample grid.

        Zoom improves detail (smaller crop → less downscale / more upscale).
        Output always fills the terminal content area (same as unzoomed fit).
        """
        view_w, view_h = _view_samples(geo)
        crop_w, crop_h = self._crop_size(img, geo)
        self._clamp(img, crop_w, crop_h)

        left = int(round(self.cx - crop_w / 2))
        top = int(round(self.cy - crop_h / 2))
        right = int(round(left + crop_w))
        bottom = int(round(top + crop_h))
        left = max(0, left)
        top = max(0, top)
        right = min(img.width, right)
        bottom = min(img.height, bottom)
        if right <= left or bottom <= top:
            cropped = img
        else:
            cropped = img.crop((left, top, right, bottom))

        tw, th = fit_pixels(cropped.width, cropped.height, view_w, view_h)
        # Prefer filling the view: allow slight stretch only via fit_pixels aspect
        if (tw, th) == cropped.size:
            return cropped
        if tw < cropped.width or th < cropped.height:
            resample = Image.Resampling.BOX
        else:
            resample = Image.Resampling.BILINEAR
        return cropped.resize((tw, th), resample=resample)

    def label(self) -> str:
        if self.zoom <= 1.0 + 1e-6:
            return "fit"
        return f"{self.zoom:.2g}x"
