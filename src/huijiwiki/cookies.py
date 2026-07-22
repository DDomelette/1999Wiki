from __future__ import annotations

from pathlib import Path

from requests.cookies import RequestsCookieJar

from .credential_schema import CanonicalCredential


class CookieLoader:
    def __init__(self, config_path: str | Path) -> None:
        self.config_path = Path(config_path)
        self._credential: CanonicalCredential | None = None

    @property
    def expected_user(self) -> str | None:
        return self._credential.expected_user if self._credential is not None else None

    def load_cookies(self) -> RequestsCookieJar:
        return self.load_bytes(self.config_path.read_bytes())

    def load_bytes(self, raw: bytes) -> RequestsCookieJar:
        self._credential = CanonicalCredential.from_bytes(raw)
        return self._credential.to_requests_cookie_jar()

    def get_cookie_expires_at(self, name: str, *, host: str) -> int | None:
        if self._credential is None:
            return None
        return self._credential.expires_at(name, host=host)

    def secret_values(self) -> tuple[tuple[str, str], ...]:
        if self._credential is None:
            return ()
        return self._credential.secret_values()

    def describe(self) -> str:
        names = self._credential.cookie_names if self._credential is not None else ()
        return (
            f"CookieLoader(config_name={self.config_path.name}, "
            f"schema=huiji_credential.v2, cookie_names={list(names)})"
        )
