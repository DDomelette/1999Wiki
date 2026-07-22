from __future__ import annotations

from argparse import Namespace
import hashlib
from pathlib import Path

import pytest

from scripts.build_wiki_mysql_rollback_receipt import build_parser as build_receipt_parser
from scripts.restore_wiki_mysql_from_receipt import validate_apply_request
from src.huiji_wiki.mysql_rollback import SOURCE_CONTAINER, SOURCE_DATABASE


def test_builder_cli_exposes_no_source_or_password_override():
    parser = build_receipt_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }

    assert option_strings == {"-h", "--help", "--receipt-id"}
    with pytest.raises(SystemExit):
        parser.parse_args(["--source-container", "other", "--receipt-id", "valid"])


def test_apply_requires_all_guards_before_mutation(tmp_path: Path):
    receipt = tmp_path / "receipt.json"
    receipt.write_bytes(b"receipt\n")
    digest = hashlib.sha256(receipt.read_bytes()).hexdigest()
    payload = {"receipt_id": "receipt-1"}
    valid = Namespace(
        apply=True,
        expected_receipt_sha256=digest,
        target_container=SOURCE_CONTAINER,
        target_database=SOURCE_DATABASE,
        confirmation="RESTORE reverse1999_wiki FROM receipt-1",
    )

    validate_apply_request(valid, payload, receipt)

    for field, value in (
        ("expected_receipt_sha256", "0" * 64),
        ("target_container", "other"),
        ("target_database", "other"),
        ("confirmation", "yes"),
    ):
        invalid = Namespace(**vars(valid))
        setattr(invalid, field, value)
        with pytest.raises(ValueError):
            validate_apply_request(invalid, payload, receipt)

