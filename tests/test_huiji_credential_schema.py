from __future__ import annotations

import json

import pytest

from src.huijiwiki.credential_schema import CanonicalCredential
from src.huijiwiki.errors import CredentialValidationError


def _cookie(
    name: str,
    value: str,
    *,
    domain: str = ".huijiwiki.com",
    path: str = "/",
    expires: int | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "expires": expires,
        "secure": True,
        "http_only": True,
    }


def _payload(cookies: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema_version": "huiji_credential.v2",
        "expected_user": "POTATO BOT",
        "cookies": cookies or [_cookie("huiji_session", "session-secret")],
    }


def test_canonical_credential_is_deterministic_and_sorted() -> None:
    payload = _payload(
        [
            _cookie("huiji_session", "session-secret"),
            _cookie("__cf_bm", "cf-secret", expires=1_900_000_000),
        ]
    )
    reversed_payload = _payload(list(reversed(payload["cookies"])))

    first = CanonicalCredential.from_payload(payload).to_bytes()
    second = CanonicalCredential.from_payload(reversed_payload).to_bytes()

    assert first == second
    assert first.endswith(b"\n")
    assert not first.startswith(b"\xef\xbb\xbf")
    decoded = json.loads(first)
    assert [item["name"] for item in decoded["cookies"]] == ["__cf_bm", "huiji_session"]


@pytest.mark.parametrize(
    "payload",
    [
        {"schema_version": "huiji_credential.v1", "expected_user": "POTATO BOT", "cookies": []},
        {"schema_version": "huiji_credential.v2", "expected_user": "", "cookies": []},
        {"schema_version": "huiji_credential.v2", "expected_user": "POTATO BOT", "cookies": []},
        {
            "schema_version": "huiji_credential.v2",
            "expected_user": "POTATO BOT",
            "cookies": [_cookie("x", "y")],
            "unknown": True,
        },
        {
            "schema_version": "huiji_credential.v2",
            "expected_user": "POTATO BOT",
            "cookies": [{**_cookie("x", "y"), "http_only": "yes"}],
        },
        {
            "schema_version": "huiji_credential.v2",
            "expected_user": "POTATO BOT",
            "cookies": [_cookie("x", "y", domain="example.com")],
        },
    ],
)
def test_canonical_credential_rejects_invalid_or_unknown_structure(payload: dict[str, object]) -> None:
    with pytest.raises(CredentialValidationError):
        CanonicalCredential.from_payload(payload)


def test_canonical_credential_rejects_duplicate_identity() -> None:
    duplicate = _cookie("huiji_session", "one")

    with pytest.raises(CredentialValidationError, match="duplicate"):
        CanonicalCredential.from_payload(_payload([duplicate, {**duplicate, "value": "two"}]))


def test_same_name_different_domain_or_path_is_preserved_in_requests_cookie_jar() -> None:
    credential = CanonicalCredential.from_payload(
        _payload(
            [
                _cookie("shared", "root", domain=".huijiwiki.com", path="/"),
                _cookie("shared", "site", domain="res1999.huijiwiki.com", path="/api.php"),
            ]
        )
    )

    jar = credential.to_requests_cookie_jar()
    identities = sorted((cookie.name, cookie.value, cookie.domain, cookie.path) for cookie in jar)

    assert identities == [
        ("shared", "root", ".huijiwiki.com", "/"),
        ("shared", "site", "res1999.huijiwiki.com", "/api.php"),
    ]


def test_expiry_uses_most_specific_cookie_for_target_host() -> None:
    credential = CanonicalCredential.from_payload(
        _payload(
            [
                _cookie("__cf_bm", "parent", domain=".huijiwiki.com", expires=10),
                _cookie("__cf_bm", "site", domain="res1999.huijiwiki.com", expires=20),
            ]
        )
    )

    assert credential.expires_at("__cf_bm", host="res1999.huijiwiki.com") == 20


def test_parser_error_never_echoes_cookie_value() -> None:
    secret = "must-never-appear"
    raw = json.dumps(_payload([{**_cookie("x", secret), "secure": "invalid"}])).encode()

    with pytest.raises(CredentialValidationError) as excinfo:
        CanonicalCredential.from_bytes(raw)

    assert secret not in str(excinfo.value)

