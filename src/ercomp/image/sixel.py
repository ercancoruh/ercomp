"""Fast DEC sixel encoder for video (pixel path — bypasses per-cell SGR)."""

from __future__ import annotations

from PIL import Image

_DCS = b"\x1bP0;0;0q"
_ST = b"\x1b\\"


def encode_sixel_rgb(
    img: Image.Image,
    width: int,
    height: int,
    *,
    colors: int = 32,
) -> bytes:
    """
    Encode RGB image as a sixel DCS sequence (bytes).

    Single-pass band packing: O(pixels + used_colors×width), not O(colors×pixels).
    """
    colors = max(2, min(256, int(colors)))
    rgb = img if img.mode == "RGB" else img.convert("RGB")
    if rgb.size != (width, height):
        rgb = rgb.resize((width, height), Image.Resampling.BOX)

    pal = rgb.quantize(
        colors=colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE
    )
    raw = pal.tobytes()
    palette = pal.getpalette() or []
    ncolors = min(colors, max(1, len(palette) // 3))

    out = bytearray()
    extend = out.extend
    append = out.append
    extend(_DCS)

    for i in range(ncolors):
        r = palette[i * 3]
        g = palette[i * 3 + 1]
        b = palette[i * 3 + 2]
        extend(
            f"#{i};2;{(r * 100 + 127) // 255};{(g * 100 + 127) // 255};{(b * 100 + 127) // 255}".encode(
                "ascii"
            )
        )

    w, h = width, height
    # Reusable plane buffers (one per palette index)
    planes = [bytearray(w) for _ in range(ncolors)]
    used_flags = bytearray(ncolors)

    for y0 in range(0, h, 6):
        band_h = min(6, h - y0)
        for i in range(ncolors):
            planes[i][:] = b"\x00" * w
        used_flags[:] = b"\x00" * ncolors

        base = y0 * w
        for dy in range(band_h):
            bit = 1 << dy
            row = base + dy * w
            for x in range(w):
                c = raw[row + x]
                if c >= ncolors:
                    continue
                planes[c][x] |= bit
                used_flags[c] = 1

        first = True
        for c in range(ncolors):
            if not used_flags[c]:
                continue
            if not first:
                append(0x24)  # $
            first = False
            extend(f"#{c}".encode("ascii"))
            _emit_rle(out, planes[c])

        append(0x2D)  # -

    if out.endswith(b"-"):
        del out[-1:]
    extend(_ST)
    return bytes(out)


def _emit_rle(out: bytearray, row: bytearray) -> None:
    """Append sixel RLE for one color plane (values 0..63)."""
    append = out.append
    extend = out.extend
    n = len(row)
    i = 0
    while i < n:
        ch = row[i]
        j = i + 1
        while j < n and row[j] == ch:
            j += 1
        run = j - i
        code = 63 + ch
        if run >= 4:
            extend(f"!{run}".encode("ascii"))
            append(code)
        else:
            for _ in range(run):
                append(code)
        i = j
