from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .errors import SensitiveValueError

SENSITIVE_KEY_PARTS = ("password", "passwd", "cookie", "secret", "token")
SAFE_KEY_EXCEPTIONS = {"content_sha256", "sha1", "download_status"}


def _assert_no_sensitive_fields(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered not in SAFE_KEY_EXCEPTIONS and any(part in lowered for part in SENSITIVE_KEY_PARTS):
                raise SensitiveValueError(f"Refusing to write sensitive field: {path + str(key)}")
            _assert_no_sensitive_fields(item, f"{path}{key}.")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_sensitive_fields(item, f"{path}{index}.")


class JsonlWriter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def write(self, record: dict[str, Any]) -> None:
        _assert_no_sensitive_fields(record)
        with self.path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
            fh.write("\n")


def write_json_file(path: str | Path, payload: dict[str, Any]) -> None:
    _assert_no_sensitive_fields(payload)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
