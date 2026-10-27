"""Stable analyzer fingerprints shared by runtime checks and corpus builds."""
from __future__ import annotations

import hashlib
from typing import Protocol

from .active_pointer import canonical_json_bytes


_BM25_PROBES = (
    "槲寄生的基础资料",
    "十四行诗的技能是什么",
    "Data:Story/304502",
    "Skill-30410111",
    "Banner_今夜星光灿烂.png",
)


class _Analyzer(Protocol):
    def analyze(self, text: str) -> list[str]: ...


def analyzer_probe_sha256(analyzer: _Analyzer) -> str:
    token_arrays = [analyzer.analyze(probe) for probe in _BM25_PROBES]
    return hashlib.sha256(canonical_json_bytes(token_arrays)).hexdigest()
