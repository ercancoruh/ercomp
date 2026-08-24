# ercomp

Terminal media **browser** — thumbnail grid in your current folder.
Photos and videos open in **new windows**; the browser stays open.

```bash
pip install ercomp
ercomp
```

On Windows, `pip install` also tries to fetch a portable **mpv** build (GPU video).
You can also run `ercomp setup-mpv` or `winget install shinchiro.mpv`.

## Controls (browser)

| Key | Action |
|-----|--------|
| Arrows | Move |
| Enter | Open folder / open file in a new window |
| Backspace / `h` | Parent folder |
| `r` | Refresh |
| `q` | Quit |

## Controls (photo / terminal video window)

| Key | Action |
|-----|--------|
| Backspace / `q` / Esc | Close window |
| `+/-` | Zoom (photos) |
| Arrows | Pan / seek |

## Optional

```bash
ercomp doctor
ercomp setup-mpv
ercomp init-config
```

## Config

`~/.config/ercomp/config.toml`:

```toml
video_backend = "auto"   # auto | terminal | mpv
video_graphics = "blocks"
cell_budget = 10000
mouse = true
```

## Development

```bash
pip install -e ".[dev]"
pytest -q
```

## License

MIT © ErCo — see [LICENSE](LICENSE) and [CHANGELOG](CHANGELOG.md).
