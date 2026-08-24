from pathlib import Path

from ercomp.config import load_config, save_default_config
from ercomp.detect import MediaKind, detect_kind, sniff_mime
from ercomp.image.term import fit_pixels
from ercomp.playlist import Nav, build_playlist, is_media


def test_fit_pixels():
    w, h = fit_pixels(200, 100, 400, 400)
    assert w == 400 and h == 200


def test_detect_png_magic(tmp_path: Path):
    p = tmp_path / "x.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    assert sniff_mime(p) == "image/png"
    assert detect_kind(p) is MediaKind.IMAGE


def test_detect_video_ext():
    assert detect_kind(Path("clip.webm")) is MediaKind.VIDEO
    assert detect_kind(Path("clip.mxf")) is MediaKind.VIDEO
    assert detect_kind(Path("photo.jfif")) is MediaKind.IMAGE


def test_playlist(tmp_path: Path):
    (tmp_path / "a.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    (tmp_path / "b.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    (tmp_path / "note.md").write_text("x")
    pl = build_playlist(tmp_path)
    assert len(pl) == 2
    assert all(p.suffix.lower() in {".jpg", ".png"} for p in pl)


def test_config_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = save_default_config()
    assert path.is_file()
    cfg = load_config()
    assert cfg.seek_seconds == 5.0
    assert cfg.mouse is True
    assert cfg.fps_cap == 24.0
    assert cfg.font_size == 1.0
    assert cfg.video_font_size == 0.0
    assert cfg.video_graphics == "blocks"
    assert cfg.video_backend == "auto"


def test_halfblock_render():
    from ercomp.image.gfx import render
    from ercomp.image.term import TermGeometry
    from PIL import Image

    geo = TermGeometry(40, 12, None, None)
    img = Image.new("RGB", (80, 40), (255, 40, 80))
    s = render(img, geo, fast=True)
    assert "▀" in s
    assert "\x1b[38;2;" in s


def test_sixel_encode():
    from ercomp.image.sixel import encode_sixel_rgb
    from PIL import Image

    img = Image.new("RGB", (24, 18), (10, 200, 40))
    raw = encode_sixel_rgb(img, 24, 18, colors=8)
    assert raw.startswith(b"\x1bP")
    assert raw.endswith(b"\x1b\\")
    assert b"#0;2;" in raw


def test_browser_scan(tmp_path: Path):
    from ercomp.browser.scan import EntryKind, list_entries
    from ercomp.playlist import dir_has_media

    media_dir = tmp_path / "shots"
    media_dir.mkdir()
    empty = tmp_path / "empty"
    empty.mkdir()
    (media_dir / "a.jpg").write_bytes(b"\xff\xd8\xff\xd9")
    (tmp_path / "root.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    (tmp_path / "readme.txt").write_text("no")

    assert dir_has_media(media_dir)
    assert not dir_has_media(empty)

    entries = list_entries(tmp_path)
    kinds = {e.name: e.kind for e in entries}
    assert "shots" in kinds and kinds["shots"] is EntryKind.DIR
    assert "root.png" in kinds and kinds["root.png"] is EntryKind.IMAGE
    assert "empty" not in kinds
    assert "readme.txt" not in kinds


def test_browser_layout():
    from ercomp.browser.ui import compute_layout, page_size

    layout = compute_layout(120, 40)
    assert layout.grid_cols >= 1
    assert layout.grid_rows >= 1
    assert page_size(layout) == layout.grid_cols * layout.grid_rows


def test_cli_help(capsys):
    from ercomp.cli import main

    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "ercomp" in out
