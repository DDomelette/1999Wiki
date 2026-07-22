from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huiji_crawler_tool.cli import main as crawler_tool_main


def main(argv: list[str] | None = None, *, tool_root: Path = ROOT) -> int:
    forwarded = list(sys.argv[1:] if argv is None else argv)
    return crawler_tool_main(["credential", "refresh", *forwarded], tool_root=tool_root)


if __name__ == "__main__":
    raise SystemExit(main())
