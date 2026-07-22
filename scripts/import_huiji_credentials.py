from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huiji_crawler_tool.cli import main as crawler_tool_main


def _translate_args(argv: list[str]) -> list[str]:
    return ["--legacy-source" if item == "--source" else item for item in argv]


def main(argv: list[str] | None = None, *, tool_root: Path = ROOT) -> int:
    forwarded = _translate_args(list(sys.argv[1:] if argv is None else argv))
    return crawler_tool_main(["credential", "import", *forwarded], tool_root=tool_root)


if __name__ == "__main__":
    raise SystemExit(main())
