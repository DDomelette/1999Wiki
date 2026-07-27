from __future__ import annotations

import http.client
import struct
import subprocess
import time
import uuid
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
VIDEO = ROOT / "frontend" / "react-app" / "public" / "videos" / "pv.mp4"
FONT_DIR = ROOT / "frontend" / "react-app" / "public" / "fonts"
FONTS_CSS = ROOT / "frontend" / "react-app" / "src" / "styles" / "fonts.css"
CADDYFILE = ROOT / "docker" / "frontend.Caddyfile"
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


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=check,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.fixture(scope="module")
def caddy_endpoint(tmp_path_factory: pytest.TempPathFactory):
    try:
        _docker("info")
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("Docker is required for the Caddy delivery contract")

    root = tmp_path_factory.mktemp("frontend-caddy")
    for directory in ("assets", "fonts", "images", "videos"):
        (root / directory).mkdir()
    (root / "index.html").write_text("<main>1999Wiki</main>", encoding="utf-8")
    (root / "assets" / "app.js").write_text(
        'const payload = "' + ("compressible-" * 1024) + '";',
        encoding="utf-8",
    )
    (root / "fonts" / "font.woff2").write_bytes(b"wOF2" + (b"f" * 4096))
    (root / "images" / "background.png").write_bytes(b"\x89PNG" + (b"i" * 4096))
    (root / "videos" / "video.mp4").write_bytes(b"video" * 2048)

    name = f"1999wiki-caddy-contract-{uuid.uuid4().hex[:12]}"
    volume_root = f"{root.resolve()}:/srv:ro"
    volume_config = f"{CADDYFILE.resolve()}:/etc/caddy/Caddyfile:ro"
    _docker(
        "run",
        "--detach",
        "--rm",
        "--name",
        name,
        "--publish",
        "127.0.0.1::8080",
        "--volume",
        volume_root,
        "--volume",
        volume_config,
        "caddy:2.11.4-alpine",
    )

    try:
        port_output = _docker("port", name, "8080/tcp").stdout.strip()
        port = int(port_output.rsplit(":", 1)[1])
        deadline = time.monotonic() + 10
        while True:
            try:
                connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                connection.request("GET", "/")
                response = connection.getresponse()
                response.read()
                connection.close()
                if response.status == 200:
                    break
            except OSError:
                pass
            if time.monotonic() >= deadline:
                logs = _docker("logs", name, check=False).stdout
                raise AssertionError(f"Caddy did not become ready:\n{logs}")
            time.sleep(0.1)
        yield "127.0.0.1", port
    finally:
        _docker("rm", "--force", name, check=False)


def _request(
    endpoint: tuple[str, int],
    path: str,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    host, port = endpoint
    connection = http.client.HTTPConnection(host, port, timeout=5)
    connection.request("GET", path, headers=headers or {})
    response = connection.getresponse()
    body = response.read()
    response_headers = {key.lower(): value for key, value in response.getheaders()}
    status = response.status
    connection.close()
    return status, response_headers, body


def test_frontend_caddy_compresses_javascript_with_zstd_and_gzip(
    caddy_endpoint: tuple[str, int],
) -> None:
    for encoding in ("zstd", "gzip"):
        status, headers, body = _request(
            caddy_endpoint,
            "/assets/app.js",
            {"Accept-Encoding": encoding},
        )
        assert status == 200
        assert headers["content-encoding"] == encoding
        assert len(body) < 4096


def test_frontend_caddy_applies_cache_policy_by_resource_identity(
    caddy_endpoint: tuple[str, int],
) -> None:
    expected = {
        "/": "no-cache",
        "/wiki": "no-cache",
        "/assets/app.js": "public, max-age=31536000, immutable",
        "/fonts/font.woff2": "public, max-age=604800",
        "/images/background.png": "public, max-age=604800",
        "/videos/video.mp4": "public, max-age=604800",
    }

    for path, cache_control in expected.items():
        status, headers, _ = _request(caddy_endpoint, path)
        assert status == 200
        assert headers["cache-control"] == cache_control

    status, headers, body = _request(
        caddy_endpoint,
        "/videos/video.mp4",
        {"Range": "bytes=0-99"},
    )
    assert status == 206
    assert headers["cache-control"] == "public, max-age=604800"
    assert headers["content-range"].startswith("bytes 0-99/")
    assert len(body) == 100
