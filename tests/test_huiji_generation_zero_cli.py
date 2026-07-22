from __future__ import annotations

from scripts.bootstrap_huiji_generation_zero import build_parser, main


def test_apply_requires_explicit_pointer_absence_and_confirmation(monkeypatch) -> None:
    called = False

    def fake_apply(_args):
        nonlocal called
        called = True
        raise ValueError("authorization rejected")

    monkeypatch.setattr("scripts.bootstrap_huiji_generation_zero._run_apply", fake_apply)
    code = main(
        [
            "apply",
            "--intent",
            "intent.json",
            "--expected-intent-sha256",
            "a" * 64,
            "--confirmation",
            "wrong",
        ]
    )
    assert code == 2
    assert called is True


def test_parser_exposes_only_inspect_apply_and_recover() -> None:
    parser = build_parser()
    action = next(item for item in parser._actions if item.dest == "command")
    assert set(action.choices) == {"inspect", "apply", "recover"}
