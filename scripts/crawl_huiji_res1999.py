from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.huiji_crawler_tool.cli import (
    build_crawl_parser,
    main as crawler_tool_main,
    parse_namespaces_values,
)
from src.huijiwiki.crawler import run_crawl


def build_parser():
    return build_crawl_parser(prog="crawl_huiji_res1999.py")


def main(
    argv: list[str] | None = None,
    *,
    project_root: Path = ROOT,
    default_credential_file: Path | None = None,
) -> int:
    forwarded = list(sys.argv[1:] if argv is None else argv)
    if default_credential_file is not None and "--config" not in forwarded:
        forwarded.extend(("--config", str(default_credential_file)))
    return crawler_tool_main(["crawl", *forwarded], tool_root=project_root)


if __name__ == "__main__":
    raise SystemExit(main())
