"""Capture immutable EVB baseline evidence.

Exit codes: 0 captured, 2 invalid or missing build output, 3 output already exists,
and 4 capture failed before a baseline was written.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.config import get_config
from src.huiji_rag.io import capture_baseline


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture create-new EventName Voice Binding baseline evidence.")
    parser.add_argument("--build", required=True, help="Huiji processed build version to capture")
    parser.add_argument("--output", required=True, type=Path, help="Create-new baseline JSON path")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    previous_output = os.environ.get("EVB_BASELINE_PATH")
    os.environ["EVB_BASELINE_PATH"] = str(args.output)
    try:
        capture_baseline(get_config(), args.build)
    except FileExistsError:
        print(f"baseline output already exists: {args.output}", file=sys.stderr)
        return 3
    except (FileNotFoundError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception as error:
        print(f"baseline capture failed: {error}", file=sys.stderr)
        return 4
    finally:
        if previous_output is None:
            os.environ.pop("EVB_BASELINE_PATH", None)
        else:
            os.environ["EVB_BASELINE_PATH"] = previous_output
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
