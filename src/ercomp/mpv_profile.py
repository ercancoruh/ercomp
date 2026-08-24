"""mpv launch flags + portable config tailored for ercomp."""

from __future__ import annotations

from pathlib import Path


def ercomp_mpv_config_dir() -> Path:
    """Writable config dir for ercomp-owned mpv settings."""
    import os

    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    d = base / "ercomp" / "mpv"
    d.mkdir(parents=True, exist_ok=True)
    conf = d / "mpv.conf"
    if not conf.is_file():
        conf.write_text(_DEFAULT_MPV_CONF, encoding="utf-8")
    input_conf = d / "input.conf"
    if not input_conf.is_file():
        input_conf.write_text(_DEFAULT_INPUT_CONF, encoding="utf-8")
    return d


_DEFAULT_MPV_CONF = """\
# ercomp mpv profile — edit freely (~/.config/ercomp/mpv/mpv.conf)
hwdec=auto-safe
vo=gpu
profile=gpu-hq
scale=ewa_lanczossharp
cscale=ewa_lanczossharp
dscale=mitchell
correct-downscaling=yes
linear-downscaling=yes
sigmoid-upscaling=yes

video-sync=display-resample
interpolation=yes
tscale=oversample

keep-aspect=yes
keep-open=yes
force-window=yes
terminal=no
osc=yes
osd-bar=yes
osd-font-size=32
osd-level=1
osd-playing-msg=${media-title}
title=ercomp — ${filename}

autofit-larger=90%x90%
geometry=50%:50%
border=yes

volume=100
volume-max=150
audio-pitch-correction=yes

screenshot-format=png
screenshot-high-bit-depth=yes
screenshot-template=ercomp-%F-%n
screenshot-directory=~~desktop/

sub-auto=fuzzy
slang=en,eng,tr,tur
alang=en,eng,tr,tur

hr-seek=yes
save-position-on-quit=yes
watch-later-directory=~~/watch_later
"""

_DEFAULT_INPUT_CONF = """\
# ercomp — mpv keys
q quit
Q quit-watch-later
ESC quit
SPACE cycle pause
RIGHT seek 5
LEFT seek -5
UP seek 60
DOWN seek -60
Shift+RIGHT seek 1 exact
Shift+LEFT seek -1 exact
f cycle fullscreen
m cycle mute
9 add volume -5
0 add volume 5
[ multiply speed 0.9
] multiply speed 1.1
BS set speed 1.0
s screenshot
S screenshot video
WHEEL_UP add volume 2
WHEEL_DOWN add volume -2
"""


def mpv_cli_args(
    path: Path,
    *,
    volume: float = 1.0,
    mute: bool = False,
    wait: bool = False,
) -> list[str]:
    """Args after the mpv executable."""
    cfg_dir = ercomp_mpv_config_dir()
    vol = max(0, min(150, int(volume * 100)))
    args = [
        f"--config-dir={cfg_dir}",
        "--force-window=yes",
        "--terminal=no",
        f"--volume={vol}",
        f"--title=ercomp — {path.name}",
        "--keep-open=yes" if not wait else "--keep-open=no",
    ]
    if mute:
        args.append("--mute=yes")
    args.append(str(path.resolve()))
    return args
