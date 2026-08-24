# Changelog

## 0.13.0

- **TUI media browser:** bare `ercomp` opens a thumbnail grid in cwd
- Photos/videos open in **new windows**; browser stays open
- Video uses **mpv** (system or portable download on Windows via `setup-mpv` / pip install)
- ercomp-owned mpv profile (`~/.config/ercomp/mpv/`) with gpu-hq defaults
- Backspace closes photo/video viewers; two-row chrome + window title
- Photo stills use Lanczos (BOX only while zooming); sharper larger thumbnails
- Windows Terminal: settings backup/restore when font session is used

## 0.12.0

- Graphics: truecolor half-blocks only (photos, GIF/WebP/APNG, video)
- Removed kitty / iTerm / sixel graphics protocols and `--protocol`
- Faster block renderer (SGR coalescing, soft cell budget for tiny fonts)
- Config simplified (`fps_cap`; legacy `fps_cap_blocks` still accepted)
- Docs and metadata updated for PyPI

## 0.11.0

- Windows Terminal: video used truecolor blocks while stills used sixel (superseded)

## Earlier

See git history for 0.10 and below.
