from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--fake-delay-seconds", type=float, default=0.0)
    parser.add_argument("--fake-exit-code", type=int, default=0)
    parser.add_argument("--fake-session-id", default="fake-thread")
    parser.add_argument("--fake-wait-file")
    parser.add_argument("--fake-stderr", default="")
    args, _ = parser.parse_known_args()

    if sys.stdin.read() != "":
        return 91
    emit({"type": "thread.started", "thread_id": args.fake_session_id})
    emit({"type": "turn.started"})
    if args.fake_delay_seconds:
        time.sleep(args.fake_delay_seconds)
    emit(
        {
            "type": "item.started",
            "item": {
                "id": "cmd-1",
                "type": "command_execution",
                "command": "python -m pytest tests/test_x.py -q",
            },
        }
    )
    if args.fake_stderr:
        print(args.fake_stderr, file=sys.stderr, flush=True)
    if args.fake_wait_file:
        wait_file = Path(args.fake_wait_file)
        while not wait_file.exists():
            time.sleep(0.05)
    emit(
        {
            "type": "item.completed",
            "item": {
                "id": "cmd-1",
                "type": "command_execution",
                "exit_code": 0,
                "aggregated_output": "2 passed",
            },
        }
    )
    if args.fake_exit_code:
        return args.fake_exit_code
    emit(
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 100,
                "cached_input_tokens": 40,
                "output_tokens": 20,
                "reasoning_output_tokens": 5,
            },
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
