"""ercomp command-line entry point."""

from __future__ import annotations

import sys
from pathlib import Path

from ercomp import __version__
from ercomp.browser import run_browser
from ercomp.config import load_config, save_default_config
from ercomp.doctor import doctor_report, setup_extras


def _run_view(path: Path) -> int:
    """Dedicated viewer window (spawned from the browser)."""
    from ercomp.detect import MediaKind, detect_kind
    from ercomp.image import ImageOpenError, show_image
    from ercomp.video import VideoError, play_video

    cfg = load_config()
    path = path.expanduser().resolve()
    if not path.is_file():
        print(f"ercomp: no such file: {path}", file=sys.stderr)
        return 1
    try:
        kind = detect_kind(path)
        if kind is MediaKind.VIDEO:
            play_video(path, cfg=cfg)
        else:
            show_image(path, dump=False, cfg=cfg)
        return 0
    except (ImageOpenError, VideoError, ValueError, OSError) as e:
        print(f"ercomp: {e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)

    if argv_list and argv_list[0] == "--view":
        if len(argv_list) < 2:
            print("ercomp --view <file>", file=sys.stderr)
            return 1
        return _run_view(Path(argv_list[1]))

    if argv_list and argv_list[0] == "doctor":
        print(doctor_report())
        return 0
    if argv_list and argv_list[0] == "setup":
        return setup_extras(dry_run="--dry-run" in argv_list)
    if argv_list and argv_list[0] == "setup-mpv":
        from ercomp.mpv_vendor import install_mpv_for_package

        install_mpv_for_package()
        return 0
    if argv_list and argv_list[0] == "init-config":
        path = save_default_config()
        print(f"wrote {path}")
        return 0
    if argv_list and argv_list[0] in {"-V", "--version", "version"}:
        print(f"ercomp {__version__}")
        return 0
    if argv_list and argv_list[0] in {"-h", "--help", "help"}:
        print(
            "ercomp — terminal media browser\n\n"
            "  ercomp              open browser in the current directory\n"
            "  ercomp doctor       environment diagnostics\n"
            "  ercomp setup-mpv    download portable mpv (Windows)\n"
            "  ercomp init-config  write default config if missing\n"
            "  ercomp --version\n"
        )
        return 0

    cfg = load_config()
    return run_browser(cfg=cfg)


if __name__ == "__main__":
    raise SystemExit(main())
