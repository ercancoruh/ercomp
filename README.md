# ercomp

Terminal media player for images, animation, and video.
**One `pip install` — nothing else to set up.**

```bash
pip install ercomp
ercomp photo.jpg
ercomp clip.mp4
ercomp ./folder/
```

Includes **Pillow** and a **bundled ffmpeg** binary (`imageio-ffmpeg`).
Frames are drawn with pure-Python **truecolor half-blocks** (▀) — exact 24-bit
color, tuned for smooth playback. No chafa, no libsixel, no extra setup step.

Requires a terminal with truecolor support (Windows Terminal, kitty, iTerm2,
most modern terminals).

## Features

| Feature | Controls |
|---------|----------|
| Zoom / pan | `+/-`, arrow keys, mouse wheel / drag |
| Playlist | `n` / `p` · open a file or directory |
| Video seek | `←` / `→`, digits then `g` or Enter |
| Audio | `m` mute, `[` `]` volume |
| Pause | Space |
| Screenshot | `s` → PNG |
| Quit | `q` / Esc |
| Config | `ercomp init-config` → `~/.config/ercomp/config.toml` |
| Diagnose | `ercomp doctor` |

## Graphics

Photos, GIFs, and video all use the same **truecolor half-block** renderer:

- Foreground = top pixel, background = bottom pixel (solid ▀)
- SGR coalescing keeps frame output small for high FPS
- Very large terminals (tiny fonts) are soft-capped so redraw stays real-time

Resolution denser styles may come later; this release prioritizes **color and FPS**.

## Config

```bash
ercomp init-config
```

Example `~/.config/ercomp/config.toml`:

```toml
fps_cap = 24.0
seek_seconds = 5.0
volume = 1.0
mute = false
mouse = true
screenshot_dir = ""
```

## Development

```bash
pip install -e ".[dev]"
ercomp doctor
pytest -q
```

## License

MIT © ErCo — see [LICENSE](LICENSE) and [CHANGELOG](CHANGELOG.md).
