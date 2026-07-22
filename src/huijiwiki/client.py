from __future__ import annotations

import time
from collections.abc import Mapping
from http.cookiejar import CookieJar
from typing import Any, Callable
from urllib.parse import urlparse

import requests

from .errors import ApiResponseError, HostViolation, SessionExpiredError
from .models import API_URL, ensure_read_only_action

TRANSIENT_STATUS_CODES = {429, 502, 503, 504}


class HuijiApiClient:
    def __init__(
        self,
        cookies: Mapping[str, str] | CookieJar | None = None,
        session: Any | None = None,
        api_url: str = API_URL,
        timeout: float = 30.0,
        sleep_fn: Callable[[float], None] = time.sleep,
        max_retries: int = 5,
        request_delay: float = 0.0,
    ) -> None:
        self.api_url = api_url
        self.timeout = timeout
        self.sleep_fn = sleep_fn
        self.max_retries = max_retries
        self.request_delay = request_delay
        self.session = session or requests.Session()
        if cookies and hasattr(self.session, "cookies"):
            self.session.cookies.update(cookies)
        if hasattr(self.session, "headers"):
            self.session.headers.update({"User-Agent": "1999SearchHuijiCrawler/1.0 read-only"})

    def _guard_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "res1999.huijiwiki.com" or parsed.path != "/api.php":
            raise HostViolation(f"Blocked API host: {url}")

    def query(self, params: dict[str, Any]) -> dict[str, Any]:
        request_params = dict(params)
        request_params.setdefault("action", "query")
        request_params.setdefault("format", "json")
        request_params.setdefault("formatversion", "2")
        ensure_read_only_action(request_params)
        self._guard_url(self.api_url)

        for attempt in range(self.max_retries + 1):
            response = self.session.get(self.api_url, params=request_params, timeout=self.timeout)
            if response.status_code in TRANSIENT_STATUS_CODES and attempt < self.max_retries:
                self.sleep_fn(float(2**attempt))
                continue
            payload = self._parse_response(response)
            if self.request_delay > 0:
                self.sleep_fn(self.request_delay)
            return payload
        raise SessionExpiredError("Request retry loop ended without a usable response")

    def _parse_response(self, response: Any) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "") if hasattr(response, "headers") else ""
        text = getattr(response, "text", "")
        if response.status_code == 403 or "Just a moment" in text or "cloudflare" in text.lower():
            raise SessionExpiredError("Cloudflare or login session blocked the API response")
        if "html" in content_type.lower() and "json" not in content_type.lower():
            raise SessionExpiredError("Expected JSON but received HTML")
        try:
            payload = response.json()
        except ValueError as exc:
            raise SessionExpiredError("Expected JSON but response could not be decoded") from exc
        if isinstance(payload, dict) and "error" in payload:
            error = payload["error"]
            if isinstance(error, dict):
                raise ApiResponseError(f"{error.get('code')}: {error.get('info')}")
            raise ApiResponseError(str(error))
        if response.status_code >= 400:
            raise ApiResponseError(f"HTTP {response.status_code}")
        return payload

    def get_siteinfo(self) -> dict[str, Any]:
        return self.query(
            {
                "meta": "siteinfo",
                "siprop": "general|namespaces|statistics",
            }
        )

    def get_userinfo(self) -> dict[str, Any]:
        return self.query(
            {
                "meta": "userinfo",
                "uiprop": "groups|rights",
            }
        )

    def close(self) -> None:
        close = getattr(self.session, "close", None)
        if callable(close):
            close()
