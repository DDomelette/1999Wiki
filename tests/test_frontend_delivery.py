from __future__ import annotations

import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "frontend" / "react-app" / "public" / "videos" / "pv.mp4"


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
