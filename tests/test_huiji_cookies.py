from __future__ import annotations

import json
import pickle

import pytest
from requests.cookies import RequestsCookieJar

from src.huijiwiki.cookies import CookieLoader
from src.huijiwiki.errors import CredentialValidationError


def _canonical_bytes() -> bytes:
    return (
        json.dumps(
            {
                "schema_version": "huiji_credential.v2",
                "expected_user": "POTATO BOT",
                "cookies": [
                    {
                        "name": "huiji_session",
                        "value": "session-value",
                        "domain": ".huijiwiki.com",
                        "path": "/",
                        "expires": None,
                        "secure": True,
                        "http_only": True,
                    },
                    {
                        "name": "__cf_bm",
                        "value": "cf-value",
                        "domain": "res1999.huijiwiki.com",
                        "path": "/",
                        "expires": 1_900_000_000,
                        "secure": True,
                        "http_only": True,
                    },
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def test_cookie_loader_reads_only_v2_without_exposing_values(tmp_path) -> None:
    config_path = tmp_path / "credential.json"
    config_path.write_bytes(_canonical_bytes())

    loader = CookieLoader(config_path)
    jar = loader.load_cookies()

    assert isinstance(jar, RequestsCookieJar)
    assert sorted(cookie.name for cookie in jar) == ["__cf_bm", "huiji_session"]
    assert loader.expected_user == "POTATO BOT"
    assert "session-value" not in loader.describe()
    assert "cf-value" not in loader.describe()
    assert "huiji_session" in loader.describe()
    assert str(tmp_path) not in loader.describe()


def test_cookie_loader_reads_cloudflare_expiry_for_target_host(tmp_path) -> None:
    config_path = tmp_path / "credential.json"
    config_path.write_bytes(_canonical_bytes())
    loader = CookieLoader(config_path)

    loader.load_cookies()

    assert loader.get_cookie_expires_at("__cf_bm", host="res1999.huijiwiki.com") == 1_900_000_000


def test_cookie_loader_missing_file_fails_without_fallback(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        CookieLoader(tmp_path / "missing.json").load_cookies()


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps({"cookies": [{"name": "x", "value": "y"}]}).encode(),
        b"huiji_session=line-session\n",
        pickle.dumps({"userinfo": {"cookie": {"huiji_session": "pickle-session"}}}),
    ],
)
def test_cookie_loader_rejects_legacy_formats(raw: bytes, tmp_path) -> None:
    config_path = tmp_path / "credential.json"
    config_path.write_bytes(raw)

    with pytest.raises(CredentialValidationError):
        CookieLoader(config_path).load_cookies()


def test_cookie_loader_malformed_binary_fails_without_echoing_bytes(tmp_path) -> None:
    config_path = tmp_path / "credential.json"
    config_path.write_bytes(b"\x80not-a-valid-pickle-secret")

    with pytest.raises(CredentialValidationError) as excinfo:
        CookieLoader(config_path).load_cookies()

    assert "secret" not in str(excinfo.value)
