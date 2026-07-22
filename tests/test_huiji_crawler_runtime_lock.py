from __future__ import annotations

from pathlib import Path

import pytest

from src.huiji_crawler_tool.errors import RuntimeLockConflict
from src.huiji_crawler_tool.runtime_lock import RuntimeLock


def test_runtime_lock_rejects_second_holder_and_releases_cleanly(tmp_path: Path) -> None:
    path = tmp_path / ".local" / "locks" / "default.lock"

    with RuntimeLock(path):
        assert path.exists()
        with pytest.raises(RuntimeLockConflict):
            with RuntimeLock(path):
                raise AssertionError("second holder must not enter")

    with RuntimeLock(path):
        assert path.exists()


def test_runtime_lock_does_not_delete_lock_file(tmp_path: Path) -> None:
    path = tmp_path / ".local" / "locks" / "default.lock"

    with RuntimeLock(path):
        pass

    assert path.is_file()
