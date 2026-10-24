from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import jieba
import pytest

from src.rag.chinese_analyzer import (
    AnalyzerConfig,
    AnalyzerIdentity,
    ChineseBM25Analyzer,
    load_dictionary_terms,
)


BASE_DICTIONARY = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "rag"
    / "resources"
    / "bm25_domain_terms.v1.txt"
)


def test_default_config_is_frozen_and_matches_the_approved_contract() -> None:
    config = AnalyzerConfig()

    assert config.to_dict() == {
        "unicode_normalization": "NFKC",
        "ascii_lowercase": True,
        "segmenter_hmm": False,
        "emit_han_bigrams": True,
        "preserve_identifiers": True,
        "preserve_filenames": True,
        "technical_pattern_version": "1",
        "merge_rule_version": "1",
    }
    with pytest.raises(FrozenInstanceError):
        config.emit_han_bigrams = False


def test_identity_contains_canonical_dictionary_and_stable_hashes() -> None:
    analyzer = ChineseBM25Analyzer(extra_terms=("额外术语", " 槲寄生 ", "额外术语"))
    identity = analyzer.identity.to_dict()

    assert identity["schema_version"] == "rag.bm25-analyzer/v1"
    assert identity["name"] == "zh-domain-word-bigram"
    assert identity["version"] == "1"
    assert identity["segmenter"] == {
        "name": "jieba",
        "version": "0.42.1",
        "hmm": False,
    }
    assert identity["dictionary_terms"] == sorted(set(identity["dictionary_terms"]))
    assert "额外术语" in identity["dictionary_terms"]
    assert "槲寄生" in identity["dictionary_terms"]
    assert all(len(identity[key]) == 64 for key in (
        "config_sha256",
        "dictionary_sha256",
        "fingerprint_sha256",
    ))
    assert AnalyzerIdentity.from_dict(identity).to_dict() == identity


def test_dictionary_hash_uses_normalized_sorted_lf_terminated_bytes(tmp_path: Path) -> None:
    dictionary = tmp_path / "terms.txt"
    dictionary.write_text(" ＡＢＣ \n槲寄生\nABC\n槲寄生\n\n", encoding="utf-8")

    analyzer = ChineseBM25Analyzer(dictionary_path=dictionary)

    assert analyzer.identity.dictionary_terms == ("ABC", "槲寄生")
    assert analyzer.identity.dictionary_bytes == "ABC\n槲寄生\n".encode("utf-8")


def test_dictionary_and_config_changes_have_separate_identity_effects() -> None:
    base = ChineseBM25Analyzer()
    changed_dictionary = ChineseBM25Analyzer(extra_terms=("新术语",))
    changed_config = AnalyzerIdentity.create(
        config=AnalyzerConfig(technical_pattern_version="2"),
        dictionary_terms=base.identity.dictionary_terms,
    )

    assert changed_dictionary.identity.dictionary_sha256 != base.identity.dictionary_sha256
    assert changed_dictionary.identity.config_sha256 == base.identity.config_sha256
    assert changed_dictionary.identity.fingerprint_sha256 != base.identity.fingerprint_sha256
    assert changed_config.dictionary_sha256 == base.identity.dictionary_sha256
    assert changed_config.config_sha256 != base.identity.config_sha256
    assert changed_config.fingerprint_sha256 != base.identity.fingerprint_sha256


def test_analyzer_identity_does_not_depend_on_input_text() -> None:
    analyzer = ChineseBM25Analyzer()
    before = analyzer.identity.to_dict()

    analyzer.analyze("槲寄生")
    analyzer.analyze("completely different 304502")

    assert analyzer.identity.to_dict() == before


def test_identity_rejects_missing_fields_and_each_tampered_hash() -> None:
    identity = ChineseBM25Analyzer().identity.to_dict()
    missing = dict(identity)
    missing.pop("segmenter")
    with pytest.raises(ValueError, match="missing"):
        AnalyzerIdentity.from_dict(missing)

    for key in ("config_sha256", "dictionary_sha256", "fingerprint_sha256"):
        tampered = json.loads(json.dumps(identity))
        tampered[key] = "0" * 64
        with pytest.raises(ValueError, match=key):
            AnalyzerIdentity.from_dict(tampered)


def test_dictionary_errors_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="dictionary"):
        load_dictionary_terms(tmp_path / "missing.txt")

    invalid_utf8 = tmp_path / "invalid.txt"
    invalid_utf8.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        load_dictionary_terms(invalid_utf8)

    control = tmp_path / "control.txt"
    control.write_text("合法\n非法\u0001术语\n", encoding="utf-8")
    with pytest.raises(ValueError, match="control"):
        load_dictionary_terms(control)


def test_base_dictionary_contains_only_reviewable_terms() -> None:
    terms = load_dictionary_terms(BASE_DICTIONARY)

    assert {
        "十四行诗",
        "槲寄生",
        "暴雨",
        "重返未来:1999",
        "神秘学家",
        "基础资料",
        "技能",
        "艺术品",
    }.issubset(terms)
    assert "重返未来：1999" in BASE_DICTIONARY.read_text(encoding="utf-8")
    assert all("\n" not in term and len(term) <= 16 for term in terms)


def test_chinese_query_emits_protected_words_and_all_adjacent_bigrams() -> None:
    tokens = ChineseBM25Analyzer().analyze("槲寄生的基础资料")

    assert "槲寄生的基础资料" not in tokens
    assert {"槲寄生", "基础资料"}.issubset(tokens)
    assert {
        "槲寄",
        "寄生",
        "生的",
        "的基",
        "基础",
        "础资",
        "资料",
    }.issubset(tokens)


def test_character_question_keeps_name_and_question_words() -> None:
    tokens = ChineseBM25Analyzer().analyze("十四行诗的技能是什么")

    assert {"十四行诗", "技能", "什么"}.issubset(tokens)
    assert {"十四", "四行", "行诗", "诗的", "的技", "技能", "能是", "是什", "什么"}.issubset(
        tokens
    )


def test_single_han_empty_whitespace_and_punctuation_are_deterministic() -> None:
    analyzer = ChineseBM25Analyzer()

    assert analyzer.analyze("雨") == ["雨"]
    assert analyzer.analyze("她") == ["她"]
    assert analyzer.analyze("") == []
    assert analyzer.analyze(" \t\r\n") == []
    assert analyzer.analyze("，。！？——") == []


def test_nfkc_and_ascii_lowercase_are_stable() -> None:
    analyzer = ChineseBM25Analyzer()

    assert analyzer.analyze("ＢＡＮＮＥＲ＿１２３") == analyzer.analyze("banner_123")
    assert analyzer.analyze("MiXeD") == ["mixed"]


def test_merge_deduplicates_same_position_but_preserves_real_repetition() -> None:
    analyzer = ChineseBM25Analyzer()

    assert analyzer.analyze("槲寄生") == ["槲寄生", "槲寄", "寄生"]
    assert analyzer.analyze("技能技能").count("技能") == 2


def test_bigram_boundaries_do_not_cross_spaces_punctuation_or_technical_atoms() -> None:
    analyzer = ChineseBM25Analyzer()

    assert "生基" not in analyzer.analyze("槲寄生 基础资料")
    assert "生基" not in analyzer.analyze("槲寄生，基础资料")
    assert "据技" not in analyzer.analyze("数据Skill-30410111技能")


@pytest.mark.parametrize(
    ("source", "whole", "parts"),
    (
        ("Data:Story/304502", "data:story/304502", {"data", "story", "304502"}),
        ("Skill-30410111", "skill-30410111", {"skill", "30410111"}),
        ("000-box-construction", "000-box-construction", {"000", "box", "construction"}),
    ),
)
def test_internal_identifiers_keep_whole_and_safe_parts(
    source: str,
    whole: str,
    parts: set[str],
) -> None:
    tokens = ChineseBM25Analyzer().analyze(source)

    assert tokens[0] == whole
    assert parts.issubset(tokens)


def test_filename_keeps_whole_atom_and_searchable_chinese() -> None:
    tokens = ChineseBM25Analyzer().analyze("Banner_今夜星光灿烂.png")

    assert tokens[0] == "banner_今夜星光灿烂.png"
    assert {"今夜", "星光", "灿烂", "今夜星光灿烂"}.intersection(tokens)
    assert {"今夜", "夜星", "星光", "光灿", "灿烂"}.issubset(tokens)
    assert {"banner_", "png"}.issubset(tokens)


def test_url_windows_path_and_long_noise_are_not_preserved_as_giant_tokens() -> None:
    analyzer = ChineseBM25Analyzer()
    url = "https://example.invalid/" + "x" * 180
    windows_path = "C:\\private\\" + "y" * 180 + ".txt"
    unbounded = "z" * 300

    assert url.lower() not in analyzer.analyze(url)
    assert windows_path.lower() not in analyzer.analyze(windows_path)
    assert unbounded not in analyzer.analyze(unbounded)


def test_two_analyzers_and_global_jieba_dictionary_do_not_pollute_each_other() -> None:
    custom = "甲乙丙丁戊"
    before = jieba.dt.FREQ.get(custom)
    first = ChineseBM25Analyzer(extra_terms=(custom,))
    second = ChineseBM25Analyzer()

    assert custom in first.analyze(custom)
    assert custom not in second.identity.dictionary_terms
    assert custom not in second.analyze(custom)
    assert jieba.dt.FREQ.get(custom) == before


def test_long_han_span_has_linear_token_output() -> None:
    source = "甲" * 2000

    tokens = ChineseBM25Analyzer().analyze(source)

    assert tokens
    assert len(tokens) <= len(source) * 3


def test_analyze_segments_matches_independent_analysis_without_crossing_boundaries() -> None:
    analyzer = ChineseBM25Analyzer()
    segments = ["槲寄生", "", "  ", "基础资料", "Skill-30410111"]

    tokens = analyzer.analyze_segments(segments)

    assert tokens == [
        token
        for segment in segments
        for token in analyzer.analyze(segment)
    ]
    assert "生基" not in tokens
    assert "skill-30410111" in tokens


def test_overlapping_protected_terms_use_stable_longer_first_order() -> None:
    analyzer = ChineseBM25Analyzer(extra_terms=("未来", "重返未来"))

    tokens = analyzer.analyze("重返未来")

    assert tokens.index("重返未来") < tokens.index("未来")
    assert tokens.count("重返未来") == 1
    assert tokens.count("未来") == 1


def test_repeated_calls_do_not_mutate_identity_or_tokens() -> None:
    analyzer = ChineseBM25Analyzer(extra_terms=("确定性术语",))
    identity = analyzer.identity.to_dict()
    expected = analyzer.analyze_segments(("确定性术语", "槲寄生的基础资料"))

    for _ in range(3):
        assert analyzer.analyze_segments(("确定性术语", "槲寄生的基础资料")) == expected
        assert analyzer.identity.to_dict() == identity


def test_analyzer_does_not_use_environment_cwd_network_or_user_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TEMP", str(tmp_path / "temp"))
    monkeypatch.setenv("TMP", str(tmp_path / "temp"))

    def fail_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr("socket.create_connection", fail_network)
    analyzer = ChineseBM25Analyzer()

    assert "槲寄生" in analyzer.analyze("槲寄生")
    assert not list(tmp_path.rglob("jieba*.cache"))


def test_fixed_probe_output_and_identity_match_across_processes(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    target_root = Path(jieba.__file__).resolve().parents[1]
    script = """
import json
from src.rag.chinese_analyzer import ChineseBM25Analyzer

analyzer = ChineseBM25Analyzer(extra_terms=("跨进程术语",))
payload = {
    "identity": analyzer.identity.to_dict(),
    "tokens": analyzer.analyze_segments((
        "槲寄生的基础资料",
        "Data:Story/304502",
        "Banner_今夜星光灿烂.png",
        "跨进程术语",
    )),
}
print(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
"""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join((str(project_root), str(target_root)))
    env["HOME"] = str(tmp_path / "home")
    env["TEMP"] = str(tmp_path / "temp")
    env["TMP"] = str(tmp_path / "temp")
    env["PYTHONIOENCODING"] = "utf-8"

    first = subprocess.check_output(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=env,
        text=True,
        encoding="utf-8",
    )
    second = subprocess.check_output(
        [sys.executable, "-c", script],
        cwd=project_root,
        env=env,
        text=True,
        encoding="utf-8",
    )

    assert first == second
    payload = json.loads(first)
    assert payload["identity"]["fingerprint_sha256"]
    assert "跨进程术语" in payload["tokens"]
