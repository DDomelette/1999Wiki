from __future__ import annotations

import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rag_eval.runner import UNEXPECTED_EXIT_CODE, main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as error:
        print(f"evaluator error: {error}", file=sys.stderr)
        raise SystemExit(UNEXPECTED_EXIT_CODE)
