from pathlib import Path

from ercomp.config import load_config, save_default_config
from ercomp.detect import MediaKind, detect_kind, sniff_mime
from ercomp.image.term import Protocol, detect_protocol, fit_pixels
from ercomp.playlist import Nav, build_playlist, is_media


def test_fit_pixels():
    w, h = fit_pixels(200, 100, 400, 400)
    assert w == 400 and h == 200


def test_protocol_force(monkeypatch):
    monkeypatch.setenv("ERCOMP_PROTOCOL", "kitty")
    assert detect_protocol() is Protocol.KITTY
    monkeypatch.setenv("ERCOMP_PROTOCOL", "blocks")
    assert detect_protocol() is Protocol.BLOCKS


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
    (tmp_path / "note.txt").write_text("x")
    pl = build_playlist(tmp_path)
    assert len(pl) == 2
    assert is_media(pl[0])
    assert Nav.NEXT.value == "next"


def test_config_roundtrip(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = save_default_config()
    assert path.is_file()
    cfg = load_config()
    assert cfg.seek_seconds == 5.0
    assert cfg.mouse is True
