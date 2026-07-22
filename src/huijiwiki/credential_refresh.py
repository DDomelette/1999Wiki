from __future__ import annotations

from pathlib import Path
from typing import Any

from .browser_client import HOMEPAGE_URL
from .credential_schema import CanonicalCredential
from .credential_store import CredentialValidationError, atomic_write_validated_credential
from .crawler import validate_expected_account


_HUIJI_COOKIE_DOMAINS = {"huijiwiki.com", "res1999.huijiwiki.com"}


def _normalize_expiry(value: object) -> int | None:
    if value in (None, "", -1, 0):
        return None
    if isinstance(value, bool):
        raise CredentialValidationError("Browser cookie expiry is invalid")
    try:
        parsed = int(float(value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise CredentialValidationError("Browser cookie expiry is invalid") from exc
    return parsed if parsed > 0 else None


def select_huiji_cookies(raw_cookies: list[dict[str, object]]) -> list[dict[str, object]]:
    selected: list[dict[str, object]] = []
    for raw in raw_cookies:
        domain = str(raw.get("domain", "")).strip().lstrip(".").lower()
        if domain not in _HUIJI_COOKIE_DOMAINS:
            continue
        name = str(raw.get("name", "")).strip()
        if not name or raw.get("value") is None:
            continue
        path = str(raw.get("path") or "/")
        selected.append(
            {
                "name": name,
                "value": str(raw["value"]),
                "domain": str(raw.get("domain") or ".huijiwiki.com"),
                "path": path if path.startswith("/") else "/",
                "expires": _normalize_expiry(raw.get("expires")),
                "secure": bool(raw.get("secure", True)),
                "http_only": bool(raw.get("httpOnly", raw.get("http_only", False))),
            }
        )
    return sorted(
        selected,
        key=lambda item: (
            str(item.get("name", "")),
            str(item.get("domain", "")),
            str(item.get("path", "")),
        ),
    )


def serialize_huiji_cookies(
    raw_cookies: list[dict[str, object]],
    *,
    expected_user: str,
) -> bytes:
    selected = select_huiji_cookies(raw_cookies)
    if not selected:
        raise CredentialValidationError("Browser session contains no Huiji cookies")
    return CanonicalCredential.from_payload(
        {
            "schema_version": "huiji_credential.v2",
            "expected_user": expected_user,
            "cookies": selected,
        }
    ).to_bytes()


def refresh_credentials(
    client: Any,
    *,
    expected_user: str,
    target: Path,
) -> dict[str, object]:
    account = validate_expected_account(client, expected_user)
    raw_cookies = client.get_cookies(HOMEPAGE_URL)
    payload = serialize_huiji_cookies(raw_cookies, expected_user=expected_user)
    inspection = atomic_write_validated_credential(target, payload, replace=True)
    return {
        "schema_version": "huiji_credential_refresh.v1",
        "status": "refreshed",
        "account": account,
        "target": inspection.to_json(),
    }
