from __future__ import annotations


class HuijiCrawlerToolError(RuntimeError):
    """Base error for the standalone crawler tool layer."""


class CrawlerConfigError(HuijiCrawlerToolError, ValueError):
    """Raised when crawler-only settings are missing or invalid."""


class ToolPathViolation(CrawlerConfigError):
    """Raised when tool-owned state resolves outside the tool root."""


class RuntimeLockConflict(HuijiCrawlerToolError):
    """Raised when another process holds the default crawler runtime lock."""


class PackageIntegrityError(HuijiCrawlerToolError):
    """Raised when immutable package content cannot be verified."""


class CrawlerEnvironmentError(HuijiCrawlerToolError):
    """Raised when Windows, Python or browser prerequisites are unsupported."""


class CliUsageError(CrawlerConfigError):
    """Raised for invalid unified CLI arguments."""
