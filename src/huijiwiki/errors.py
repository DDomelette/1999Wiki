from __future__ import annotations


class HuijiCrawlerError(RuntimeError):
    """Base error for the HuijiWiki crawler."""


class ReadOnlyViolation(HuijiCrawlerError):
    """Raised when code attempts to use a write-like MediaWiki action."""


class HostViolation(HuijiCrawlerError):
    """Raised when a request target is outside res1999.huijiwiki.com."""


class SessionExpiredError(HuijiCrawlerError):
    """Raised when cookies are missing, expired, or blocked by Cloudflare."""


class CredentialLoadError(HuijiCrawlerError):
    """Raised when the project-local crawler credential cannot be loaded."""


class CredentialValidationError(ValueError):
    """Raised when a credential payload does not match the supported schema."""


class AccountMismatchError(HuijiCrawlerError):
    """Raised when the authenticated account is not the expected bot account."""


class ApiResponseError(HuijiCrawlerError):
    """Raised when the MediaWiki API returns an error object."""


class SensitiveValueError(HuijiCrawlerError):
    """Raised when an output record contains secret-bearing fields."""
