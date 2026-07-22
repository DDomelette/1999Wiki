from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from requests.cookies import RequestsCookieJar

from .errors import CredentialValidationError


CREDENTIAL_SCHEMA_VERSION = "huiji_credential.v2"
_TOP_LEVEL_KEYS = {"schema_version", "expected_user", "cookies"}
_COOKIE_KEYS = {
    "name",
    "value",
    "domain",
    "path",
    "expires",
    "secure",
    "http_only",
}


def _valid_huiji_domain(domain: str) -> bool:
    normalized = domain.lstrip(".").casefold()
    return normalized == "huijiwiki.com" or normalized.endswith(".huijiwiki.com")


@dataclass(frozen=True)
class CredentialCookie:
    name: str
    value: str
    domain: str
    path: str
    expires: int | None
    secure: bool
    http_only: bool

    @classmethod
    def from_payload(cls, payload: object) -> "CredentialCookie":
        if not isinstance(payload, dict) or set(payload) != _COOKIE_KEYS:
            raise CredentialValidationError("Credential cookie fields are invalid")
        name = payload["name"]
        value = payload["value"]
        domain = payload["domain"]
        path = payload["path"]
        expires = payload["expires"]
        secure = payload["secure"]
        http_only = payload["http_only"]
        if not isinstance(name, str) or not name.strip():
            raise CredentialValidationError("Credential cookie name is invalid")
        if not isinstance(value, str):
            raise CredentialValidationError("Credential cookie value type is invalid")
        if not isinstance(domain, str) or not domain.strip() or not _valid_huiji_domain(domain):
            raise CredentialValidationError("Credential cookie domain is invalid")
        if not isinstance(path, str) or not path.startswith("/"):
            raise CredentialValidationError("Credential cookie path is invalid")
        if expires is not None and (isinstance(expires, bool) or not isinstance(expires, int)):
            raise CredentialValidationError("Credential cookie expiry is invalid")
        if not isinstance(secure, bool) or not isinstance(http_only, bool):
            raise CredentialValidationError("Credential cookie flags are invalid")
        normalized_domain = domain.strip().casefold()
        if domain.strip().startswith("."):
            normalized_domain = "." + normalized_domain.lstrip(".")
        return cls(
            name=name.strip(),
            value=value,
            domain=normalized_domain,
            path=PurePosixPath(path).as_posix(),
            expires=expires,
            secure=secure,
            http_only=http_only,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": self.value,
            "domain": self.domain,
            "path": self.path,
            "expires": self.expires,
            "secure": self.secure,
            "http_only": self.http_only,
        }


@dataclass(frozen=True)
class CanonicalCredential:
    expected_user: str
    cookies: tuple[CredentialCookie, ...]

    @classmethod
    def from_payload(cls, payload: object) -> "CanonicalCredential":
        if not isinstance(payload, dict) or set(payload) != _TOP_LEVEL_KEYS:
            raise CredentialValidationError("Credential document fields are invalid")
        if payload.get("schema_version") != CREDENTIAL_SCHEMA_VERSION:
            raise CredentialValidationError(
                f"Credential schema_version must be {CREDENTIAL_SCHEMA_VERSION}"
            )
        expected_user = payload.get("expected_user")
        if not isinstance(expected_user, str) or not expected_user.strip():
            raise CredentialValidationError("Credential expected_user is invalid")
        raw_cookies = payload.get("cookies")
        if not isinstance(raw_cookies, list) or not raw_cookies:
            raise CredentialValidationError("Credential must contain at least one cookie")
        cookies = tuple(
            sorted(
                (CredentialCookie.from_payload(item) for item in raw_cookies),
                key=lambda item: (item.name, item.domain, item.path),
            )
        )
        identities: set[tuple[str, str, str]] = set()
        for cookie in cookies:
            identity = (cookie.name, cookie.domain.casefold(), cookie.path)
            if identity in identities:
                raise CredentialValidationError("Credential contains a duplicate cookie identity")
            identities.add(identity)
        return cls(expected_user=expected_user.strip(), cookies=cookies)

    @classmethod
    def from_bytes(cls, raw: bytes) -> "CanonicalCredential":
        if not raw:
            raise CredentialValidationError("Credential payload is empty")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CredentialValidationError("Credential payload is not valid UTF-8 JSON") from exc
        return cls.from_payload(payload)

    @property
    def cookie_names(self) -> tuple[str, ...]:
        return tuple(sorted({cookie.name for cookie in self.cookies}))

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": CREDENTIAL_SCHEMA_VERSION,
            "expected_user": self.expected_user,
            "cookies": [cookie.to_payload() for cookie in self.cookies],
        }

    def to_bytes(self) -> bytes:
        return (
            json.dumps(
                self.to_payload(),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

    def to_requests_cookie_jar(self) -> RequestsCookieJar:
        jar = RequestsCookieJar()
        for cookie in self.cookies:
            rest: dict[str, Any] = {}
            if cookie.http_only:
                rest["HttpOnly"] = True
            jar.set(
                cookie.name,
                cookie.value,
                domain=cookie.domain,
                path=cookie.path,
                secure=cookie.secure,
                expires=cookie.expires,
                rest=rest,
            )
        return jar

    def secret_values(self) -> tuple[tuple[str, str], ...]:
        return tuple((cookie.name, cookie.value) for cookie in self.cookies)

    def expires_at(self, name: str, *, host: str) -> int | None:
        normalized_host = host.casefold().strip(".")
        matches: list[CredentialCookie] = []
        for cookie in self.cookies:
            if cookie.name != name:
                continue
            domain = cookie.domain.casefold().lstrip(".")
            if normalized_host == domain or normalized_host.endswith("." + domain):
                matches.append(cookie)
        if not matches:
            return None
        matches.sort(
            key=lambda cookie: (len(cookie.domain.lstrip(".")), len(cookie.path)),
            reverse=True,
        )
        return matches[0].expires
