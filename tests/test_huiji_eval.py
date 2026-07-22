from types import SimpleNamespace

from scripts.evaluate_huiji_rag import apply_runtime_overrides, compute_recall, evaluate_result, summarize_evaluations


def test_compute_recall_counts_expected_ids():
    assert compute_recall(["a", "b"], ["b", "c"]) == 0.5
    assert compute_recall([], ["b"]) == 0.0
    assert compute_recall(["a"], []) == 1.0


def test_evaluate_result_reports_core_violations():
    row = {
        "id": "skill_sonetto",
        "query": "十四行诗的技能是什么",
        "expected_entity": "十四行诗",
        "expected_intent": "skill",
        "required_sections": ["skill"],
        "required_media_types": ["image"],
        "forbid_media_types": ["voice"],
    }
    result = {
        "planning_status": "llm",
        "route": {"entity": "金蜜儿", "intent": "intro"},
        "sources": [{
            "name": "金蜜儿",
            "section_kind": "profile",
            "child_id": "char:9999/profile:0000",
            "parent_id": "char:9999/profile",
            "content": "D:\\local\\leak.png",
            "debug": {
                "bm25_rank": 2,
                "dense_rank": 7,
                "exact_entity_bonus": 0.3,
                "ignored": "not ranking-related",
            },
        }],
        "media": [{
            "media_id": "voice-1",
            "asset_type": "voice",
            "url": "file://voice.ogg",
        }],
        "omitted_actions": [],
        "failure_actions": [],
    }

    evaluated = evaluate_result(row, result)

    assert evaluated["passed"] is False
    assert set(evaluated["violations"]) >= {
        "wrong_entity",
        "wrong_intent",
        "missing_required_section",
        "missing_required_media",
        "forbidden_media_type",
        "local_path_leak",
        "voice_auto_leak",
    }
    assert evaluated["top_sources"][0]["ranking_debug"] == {
        "bm25_rank": 2,
        "dense_rank": 7,
        "exact_entity_bonus": 0.3,
    }


def test_summarize_evaluations_reports_metrics_thresholds_and_failed_cases():
    rows = [
        {
            "id": "ok",
            "expected_entity": "十四行诗",
            "expected_intent": "intro",
            "entity": "十四行诗",
            "intent": "intro",
            "violations": [],
            "passed": True,
        },
        {
            "id": "bad",
            "expected_entity": "玛蒂尔达",
            "expected_intent": "skill",
            "entity": "槲寄生",
            "intent": "intro",
            "violations": ["wrong_entity", "wrong_intent", "local_path_leak"],
            "passed": False,
        },
    ]

    summary = summarize_evaluations(
        rows,
        thresholds={
            "pass_rate": {"min": 0.75},
            "entity_accuracy": {"min": 0.75},
            "local_path_leak_rate": {"max": 0.0},
        },
    )

    assert summary["query_count"] == 2
    assert summary["passed_count"] == 1
    assert summary["failed_count"] == 1
    assert summary["metrics"]["pass_rate"] == 0.5
    assert summary["metrics"]["entity_accuracy"] == 0.5
    assert summary["metrics"]["intent_accuracy"] == 0.5
    assert summary["metrics"]["local_path_leak_rate"] == 0.5
    assert summary["failed_cases"] == [{"id": "bad", "violations": ["wrong_entity", "wrong_intent", "local_path_leak"]}]
    assert set(summary["threshold_violations"]) == {
        "pass_rate below min 0.75: 0.5",
        "entity_accuracy below min 0.75: 0.5",
        "local_path_leak_rate above max 0.0: 0.5",
    }


def test_apply_runtime_overrides_only_changes_in_memory_reranker_flag():
    cfg = SimpleNamespace(reranker=SimpleNamespace(enabled=False))

    apply_runtime_overrides(cfg, reranker_enabled=True)

    assert cfg.reranker.enabled is True
