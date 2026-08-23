"""ercomp command-line entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ercomp import __version__
from ercomp.config import load_config, save_default_config
from ercomp.detect import MediaKind, detect_kind
from ercomp.doctor import doctor_report, setup_extras
from ercomp.image import ImageOpenError, image_info, show_image
from ercomp.image.term import Protocol
from ercomp.playlist import Nav, build_playlist, index_of
from ercomp.video import VideoError, play_video, video_info


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ercomp",
        description="Terminal media player for images and video.",
        epilog="Commands: ercomp doctor | ercomp <file|dir>  (pip install is enough)",
    )
    p.add_argument("path", nargs="?", help="file/dir to open, or: doctor | init-config")
    p.add_argument(
        "--protocol",
        choices=[x.value for x in Protocol],
        help="force protocol (default: config/auto)",
    )
    p.add_argument("--info", action="store_true", help="print metadata only")
    p.add_argument("--dump", action="store_true", help="print once without alt-screen")
    p.add_argument("--dry-run", action="store_true", help="ignored (setup is a no-op)")
    p.add_argument("-V", "--version", action="version", version=f"ercomp {__version__}")
    return p


def _open_one(path: Path, *, protocol: str | None, dump: bool, cfg) -> Nav:
    kind = detect_kind(path)
    if kind is MediaKind.VIDEO:
        return play_video(path, protocol_name=protocol, cfg=cfg)
    if kind is MediaKind.UNKNOWN:
        kind = MediaKind.IMAGE
    if kind is MediaKind.IMAGE:
        return show_image(path, protocol_name=protocol, dump=dump, cfg=cfg)
    print(f"ercomp: unsupported media: {path}", file=sys.stderr)
    return Nav.QUIT


def _run_playlist(path: Path, *, protocol: str | None, dump: bool, cfg) -> int:
    playlist = build_playlist(path)
    if not playlist:
        print(f"ercomp: no media in {path}", file=sys.stderr)
        return 1

    if path.is_file():
        idx = index_of(playlist, path)
    else:
        idx = 0

    if dump or len(playlist) == 1:
        try:
            _open_one(playlist[idx], protocol=protocol, dump=dump, cfg=cfg)
            return 0
        except (ImageOpenError, VideoError, ValueError) as e:
            print(f"ercomp: {e}", file=sys.stderr)
            return 1

    while True:
        current = playlist[idx]
        try:
            nav = _open_one(current, protocol=protocol, dump=False, cfg=cfg)
        except (ImageOpenError, VideoError, ValueError) as e:
            print(f"ercomp: {e}", file=sys.stderr)
            # skip broken file
            nav = Nav.NEXT

        if nav is Nav.QUIT:
            return 0
        if nav is Nav.NEXT:
            idx = (idx + 1) % len(playlist)
        elif nav is Nav.PREV:
            idx = (idx - 1) % len(playlist)
        else:
            return 0


def main(argv: list[str] | None = None) -> int:
    argv_list = list(sys.argv[1:] if argv is None else argv)

    if argv_list and argv_list[0] == "doctor":
        print(doctor_report())
        return 0
    if argv_list and argv_list[0] == "setup":
        return setup_extras(dry_run="--dry-run" in argv_list)
    if argv_list and argv_list[0] == "init-config":
        path = save_default_config()
        print(f"wrote {path}")
        return 0

    parser = build_parser()
    args = parser.parse_args(argv_list)

    if not args.path:
        parser.print_help()
        return 0

    path = Path(args.path).expanduser()
    if not path.exists():
        print(f"ercomp: no such file: {path}", file=sys.stderr)
        return 1

    cfg = load_config()
    protocol = args.protocol

    if args.info:
        if not path.is_file():
            print("ercomp: --info requires a file", file=sys.stderr)
            return 1
        try:
            kind = detect_kind(path)
            if kind is MediaKind.VIDEO:
                print(video_info(path))
            else:
                print(image_info(path, protocol_name=protocol))
            return 0
        except (ImageOpenError, VideoError) as e:
            print(f"ercomp: {e}", file=sys.stderr)
            return 1

    return _run_playlist(path, protocol=protocol, dump=args.dump, cfg=cfg)


if __name__ == "__main__":
    raise SystemExit(main())
