from __future__ import annotations

import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "frontend" / "react-app" / "public" / "videos" / "pv.mp4"
FONT_DIR = ROOT / "frontend" / "react-app" / "public" / "fonts"
FONTS_CSS = ROOT / "frontend" / "react-app" / "src" / "styles" / "fonts.css"
ORIGINAL_NOTO_OTF_BYTES = 50_064_540


def _top_level_atoms(path: Path) -> list[tuple[str, int]]:
    atoms: list[tuple[str, int]] = []
    file_size = path.stat().st_size
    offset = 0

    with path.open("rb") as stream:
        while offset + 8 <= file_size:
            stream.seek(offset)
            size, kind = struct.unpack(">I4s", stream.read(8))
            header_size = 8
            if size == 1:
                size = struct.unpack(">Q", stream.read(8))[0]
                header_size = 16
            elif size == 0:
                size = file_size - offset

            assert size >= header_size, f"invalid MP4 atom size at offset {offset}"
            atoms.append((kind.decode("ascii"), offset))
            offset += size

    return atoms


def test_home_video_is_small_and_faststart() -> None:
    atoms = dict(_top_level_atoms(VIDEO))

    assert VIDEO.stat().st_size <= 20 * 1024 * 1024
    assert atoms["moov"] < atoms["mdat"]


def test_chinese_fonts_use_smaller_woff2_payloads() -> None:
    css = FONTS_CSS.read_text(encoding="utf-8")
    font_names = (
        "noto-serif-sc-regular.woff2",
        "noto-serif-sc-bold.woff2",
    )

    assert all(name in css for name in font_names)
    assert "noto-serif-sc-regular.otf" not in css
    assert "noto-serif-sc-bold.otf" not in css
    assert css.count("font-display: optional") == 2

    font_payloads = [(FONT_DIR / name).read_bytes() for name in font_names]
    assert all(payload[:4] == b"wOF2" for payload in font_payloads)
    assert sum(len(payload) for payload in font_payloads) < ORIGINAL_NOTO_OTF_BYTES
