from __future__ import annotations

import subprocess
import sys

from scripts.import_huiji_wiki_v3 import APPLY_CONFIRMATION, build_parser, inspection_evidence_name


def test_formal_import_cli_defaults_to_inspect():
    args = build_parser().parse_args([])

    assert args.apply is False
    assert args.confirmation == ""


def test_formal_import_cli_help_loads_without_side_effects():
    result = subprocess.run(
        [sys.executable, "scripts/import_huiji_wiki_v3.py", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert APPLY_CONFIRMATION not in result.stderr
    assert "--expected-handoff-sha256" in result.stdout


def test_formal_import_cli_separates_pre_and_post_import_inspection_evidence():
    assert inspection_evidence_name(already_installed=False) == "inspection.pre-import.v1.json"
    assert inspection_evidence_name(already_installed=True) == "inspection.post-import.v1.json"
