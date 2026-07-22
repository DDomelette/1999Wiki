from __future__ import annotations

import json
import pickle
from collections.abc import Iterable

from .credential_schema import CanonicalCredential
from .errors import CredentialValidationError


def _allowed_domain(value: object) -> bool:
    domain = str(value or ".huijiwiki.com").strip().lstrip(".").casefold()
    return domain == "huijiwiki.com" or domain.endswith(".huijiwiki.com")


def _normalize_expiry(value: object) -> int | None:
    if value in (None, "", -1, 0):
        return None
    if isinstance(value, bool):
        raise CredentialValidationError("Legacy cookie expiry is invalid")
    try:
        parsed = int(float(value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise CredentialValidationError("Legacy cookie expiry is invalid") from exc
    return parsed if parsed > 0 else None


def _cookie_payload(
    *,
    name: object,
    value: object,
    domain: object = ".huijiwiki.com",
    path: object = "/",
    expires: object = None,
    secure: object = True,
    http_only: object = False,
) -> dict[str, object] | None:
    rendered_name = str(name or "").strip()
    if not rendered_name or value is None or not _allowed_domain(domain):
        return None
    rendered_domain = str(domain or ".huijiwiki.com").strip()
    rendered_path = str(path or "/")
    if not rendered_path.startswith("/"):
        rendered_path = "/"
    return {
        "name": rendered_name,
        "value": str(value),
        "domain": rendered_domain,
        "path": rendered_path,
        "expires": _normalize_expiry(expires),
        "secure": bool(secure),
        "http_only": bool(http_only),
    }


def _iter_cookie_payloads(container: object) -> Iterable[dict[str, object]]:
    if isinstance(container, dict):
        if isinstance(container.get("cookies"), list):
            yield from _iter_cookie_payloads(container["cookies"])
            return
        userinfo = container.get("userinfo")
        if isinstance(userinfo, dict) and "cookie" in userinfo:
            yield from _iter_cookie_payloads(userinfo["cookie"])
            return
        for name, value in container.items():
            if isinstance(value, str):
                cookie = _cookie_payload(name=name, value=value)
                if cookie is not None:
                    yield cookie
        return
    if isinstance(container, list):
        values = container
    elif hasattr(container, "__iter__") and not isinstance(container, (str, bytes)):
        values = list(container)
    else:
        values = []
    for item in values:
        if isinstance(item, dict):
            cookie = _cookie_payload(
                name=item.get("name"),
                value=item.get("value"),
                domain=item.get("domain", ".huijiwiki.com"),
                path=item.get("path", "/"),
                expires=item.get("expires"),
                secure=item.get("secure", True),
                http_only=item.get("http_only", item.get("httpOnly", False)),
            )
        else:
            rest = getattr(item, "_rest", {})
            cookie = _cookie_payload(
                name=getattr(item, "name", None),
                value=getattr(item, "value", None),
                domain=getattr(item, "domain", ".huijiwiki.com"),
                path=getattr(item, "path", "/"),
                expires=getattr(item, "expires", None),
                secure=getattr(item, "secure", True),
                http_only=isinstance(rest, dict) and "HttpOnly" in rest,
            )
        if cookie is not None:
            yield cookie


def _parse_text(text: str) -> object:
    stripped = text.strip()
    if not stripped:
        raise CredentialValidationError("Legacy credential payload is empty")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        cookies: dict[str, str] = {}
        for line in stripped.splitlines():
            cleaned = line.strip()
            if not cleaned or cleaned.startswith("#"):
                continue
            if "=" not in cleaned:
                raise CredentialValidationError("Legacy credential text format is invalid")
            name, value = cleaned.split("=", 1)
            if not name.strip():
                raise CredentialValidationError("Legacy credential text format is invalid")
            cookies[name.strip()] = value.strip()
        if not cookies:
            raise CredentialValidationError("Legacy credential contains no cookies")
        return cookies


def decode_legacy_credential(raw: bytes, *, expected_user: str) -> CanonicalCredential:
    if not raw:
        raise CredentialValidationError("Legacy credential payload is empty")
    if not isinstance(expected_user, str) or not expected_user.strip():
        raise CredentialValidationError("Legacy import expected_user is invalid")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            payload = pickle.loads(raw)
        except Exception as exc:
            raise CredentialValidationError("Legacy binary credential is not parseable") from exc
    else:
        payload = _parse_text(text)
    if isinstance(payload, dict) and payload.get("schema_version") == "huiji_credential.v2":
        credential = CanonicalCredential.from_payload(payload)
        if credential.expected_user != expected_user.strip():
            raise CredentialValidationError("Credential expected_user does not match import target")
        return credential
    cookies = list(_iter_cookie_payloads(payload))
    if not cookies:
        raise CredentialValidationError("Legacy credential contains no Huiji cookies")
    return CanonicalCredential.from_payload(
        {
            "schema_version": "huiji_credential.v2",
            "expected_user": expected_user.strip(),
            "cookies": cookies,
        }
    )
