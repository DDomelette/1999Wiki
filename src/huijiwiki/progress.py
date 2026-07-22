from __future__ import annotations

import sys
import time
from typing import TextIO


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{secs:02d}s"
    return f"{minutes}m{secs:02d}s"


def render_bar(current: int, total: int | None, width: int = 20) -> str:
    if not total:
        return f"{current}"
    current = min(current, total)
    filled = int(width * current / total)
    return f"[{'#' * filled}{'.' * (width - filled)}] {current}/{total}"


class ProgressReporter:
    def __init__(
        self,
        enabled: bool = True,
        log_every: int = 100,
        cf_cookie_expires_at: float | None = None,
        stream: TextIO | None = None,
        clock=time.time,
    ) -> None:
        self.enabled = enabled
        self.log_every = max(1, int(log_every))
        self.cf_cookie_expires_at = cf_cookie_expires_at
        self.stream = stream or sys.stderr
        self.clock = clock
        self.started_at = self.clock()

    def stage(self, message: str) -> None:
        if not self.enabled:
            return
        self._write(f"[progress] {message} | {self._cookie_text()}")

    def item(self, stage: str, current: int, total: int | None = None, title: str | None = None) -> None:
        if not self.enabled:
            return
        if current != 1 and current % self.log_every != 0 and (total is None or current != total):
            return
        elapsed = max(0.001, self.clock() - self.started_at)
        rate = current / elapsed
        eta = None
        if total and rate > 0 and current <= total:
            eta = (total - current) / rate
        title_part = f" | current: {title}" if title else ""
        self._write(
            f"[progress] {stage} {render_bar(current, total)} "
            f"| rate={rate:.2f}/s | ETA={format_duration(eta)} | {self._cookie_text()}{title_part}"
        )

    def _cookie_text(self) -> str:
        if self.cf_cookie_expires_at is None:
            return "Cloudflare cookie: unknown"
        remaining = self.cf_cookie_expires_at - self.clock()
        if remaining < 0:
            return f"Cloudflare cookie: expired {format_duration(-remaining)} ago"
        return f"Cloudflare cookie: {format_duration(remaining)}"

    def _write(self, message: str) -> None:
        print(message, file=self.stream, flush=True)
