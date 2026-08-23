# ercomp

Terminal media player — images, animation, video. **One package, nothing else to install.**

```bash
pip install ercomp
ercomp photo.jpg
ercomp clip.mp4
ercomp ./photos/
```

Pulls in **Pillow** + **bundled ffmpeg** (`imageio-ffmpeg`). Graphics protocols (kitty / iterm / sixel / blocks) are pure Python — no chafa, no libsixel, no `ercomp setup`.

## Features

| Feature | Keys / notes |
|---------|----------------|
| Zoom / pan | `+/-`, arrows, mouse wheel / drag |
| Playlist | `n` / `p` · file or directory |
| Video seek | `←`/`→`, digits+`g` / Enter |
| Audio | `m` mute, `[` `]` volume |
| Screenshot | `s` → PNG |
| Config | `ercomp init-config` → `~/.config/ercomp/config.toml` |

## Protocols

Auto: **kitty → iterm → sixel → blocks**. Override: `--protocol` or config.

## Dev

```bash
pip install -e .
ercomp doctor
pytest -q
```

## License

MIT
