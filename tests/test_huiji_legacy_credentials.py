from __future__ import annotations

import json
import pickle
from pathlib import Path

import pytest
from requests.cookies import RequestsCookieJar

from src.huijiwiki.errors import CredentialValidationError
from src.huijiwiki.legacy_credentials import decode_legacy_credential


def test_legacy_decoder_supports_unversioned_json_explicitly() -> None:
    raw = json.dumps(
        {
            "cookies": [
                {
                    "name": "huiji_session",
                    "value": "session-secret",
                    "domain": ".huijiwiki.com",
                    "path": "/",
                }
            ]
        }
    ).encode()

    credential = decode_legacy_credential(raw, expected_user="POTATO BOT")

    assert credential.expected_user == "POTATO BOT"
    assert credential.cookie_names == ("huiji_session",)
    assert json.loads(credential.to_bytes())["schema_version"] == "huiji_credential.v2"


def test_legacy_decoder_supports_line_format_explicitly() -> None:
    credential = decode_legacy_credential(
        b"huiji_session=line-session\n__cf_bm=line-cf\n",
        expected_user="POTATO BOT",
    )

    assert credential.cookie_names == ("__cf_bm", "huiji_session")


def test_legacy_decoder_supports_pickled_cookie_jar_explicitly() -> None:
    jar = RequestsCookieJar()
    jar.set("huiji_session", "session-secret", domain=".huijiwiki.com", path="/")
    jar.set("__cf_bm", "cf-secret", domain=".huijiwiki.com", path="/", expires=1_900_000_000)
    raw = pickle.dumps({"userinfo": {"cookie": jar}})

    credential = decode_legacy_credential(raw, expected_user="POTATO BOT")

    assert credential.cookie_names == ("__cf_bm", "huiji_session")
    assert credential.expires_at("__cf_bm", host="res1999.huijiwiki.com") == 1_900_000_000


def test_legacy_decoder_drops_unrelated_domains() -> None:
    raw = json.dumps(
        {
            "cookies": [
                {"name": "huiji_session", "value": "good", "domain": ".huijiwiki.com"},
                {"name": "unrelated", "value": "bad", "domain": "example.com"},
            ]
        }
    ).encode()

    credential = decode_legacy_credential(raw, expected_user="POTATO BOT")

    assert credential.cookie_names == ("huiji_session",)


@pytest.mark.parametrize("raw", [b"", b"not a cookie file", b"\x80broken-pickle"])
def test_legacy_decoder_rejects_empty_or_malformed_input(raw: bytes) -> None:
    with pytest.raises(CredentialValidationError):
        decode_legacy_credential(raw, expected_user="POTATO BOT")


def test_stable_cookie_loader_source_has_no_pickle_or_legacy_import() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "src" / "huijiwiki" / "cookies.py").read_text(encoding="utf-8")

    assert "import pickle" not in source
    assert "legacy_credentials" not in source

