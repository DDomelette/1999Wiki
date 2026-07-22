import importlib.util
import time

from src.rag.packet_policy import PacketPolicy, get_packet_policy
from src.rag import packet_policy
from src.rag import retrieval_budget


def test_packet_policies_declare_backward_compatible_source_coverage():
    default_policy = PacketPolicy(name="default", sections=(), output_mode="rag")
    skill_policy = get_packet_policy("character", "skill")
    voice_policy = get_packet_policy("character", "voice")

    assert default_policy.coverage_mode == "at_least_one"
    assert default_policy.source_target == 1
    assert skill_policy.coverage_mode == "all_available"
    assert voice_policy.coverage_mode == "fixed"
    assert voice_policy.source_target == 8


def test_compose_packet_policies_preserves_intents_and_builds_ordered_unions():
    bundle = packet_policy.compose_packet_policies(
        "character",
        ("skill", "voice", "media", "skill"),
    )

    assert bundle.requested_intents == ("skill", "voice", "media")
    assert bundle.policies == (
        get_packet_policy("character", "skill"),
        get_packet_policy("character", "voice"),
        get_packet_policy("character", "media"),
    )
    assert bundle.sections == ("skills", "voice", "media", "skins", "profile")
    assert bundle.media_types == ("skill", "voice", "portrait", "image")
    assert bundle.context_budget_chars == 9000
    assert bundle.expansion_policy.sections == bundle.sections


def test_canonical_and_legacy_section_capabilities_are_explicit():
    canonical = packet_policy.compose_packet_policies(
        "character", ("item", "culture", "udimo"), "v3"
    )
    legacy = packet_policy.compose_packet_policies(
        "character", ("item", "culture", "udimo"), "legacy"
    )

    assert canonical.sections == ("collection", "culture_dossier", "udimo")
    assert legacy.sections == (
        "collection", "culture", "culture_dossier", "items", "item", "udimo"
    )


def test_retrieval_budget_module_exists():
    assert importlib.util.find_spec("src.rag.retrieval_budget") is not None


def test_required_source_count_uses_exact_text_rows_and_ignores_media_records():
    bundle = packet_policy.compose_packet_policies(
        "character",
        ("skill", "voice", "culture", "item"),
    )
    exact_rows_by_intent = {
        "skill": [{"child_id": f"skill-{index}"} for index in range(4)],
        "voice": [{"child_id": f"voice-{index}"} for index in range(9)],
        "culture": [{"child_id": f"culture-{index}"} for index in range(2)],
        "item": [],
        "playable_media": [{"media_id": f"media-{index}"} for index in range(100)],
    }

    assert retrieval_budget.calculate_required_source_count(
        bundle,
        exact_rows_by_intent,
        voice_page_size=5,
    ) == 10


def test_candidate_k_uses_source_requirements_with_an_absolute_cap():
    assert retrieval_budget.calculate_candidate_k(20, 10, 4, 100) == 40
    assert retrieval_budget.calculate_candidate_k(60, 2, 4, 100) == 60
    assert retrieval_budget.calculate_candidate_k(20, 30, 4, 100) == 100


def test_voice_page_size_is_clamped_to_the_configured_range():
    assert retrieval_budget.clamp_voice_page_size(0, 20) == 1
    assert retrieval_budget.clamp_voice_page_size(8, 20) == 8
    assert retrieval_budget.clamp_voice_page_size(21, 20) == 20


def _row(child_id, intent=None, *, score=0.0, text="x"):
    row = {"child_id": child_id, "score": score, "text": text}
    if intent:
        row["matched_intents"] = (intent,)
    return row


def test_allocator_deduplicates_children_and_does_not_add_unmatched_filler():
    bundle = packet_policy.compose_packet_policies("character", ("skill", "voice"))
    skill_one = _row("skill-1", "skill", score=0.6)
    skill_two = _row("skill-2", "skill", score=0.7)
    voice = _row("voice-1", "voice", score=0.8)
    spare = _row("profile-1", score=0.99)

    result = retrieval_budget.allocate_sources(
        [spare, voice, skill_two, skill_one],
        {
            "skill": [skill_one, skill_two],
            "voice": [{**voice, "matched_intents": ("voice", "media")}],
        },
        bundle,
        max_sources=4,
        context_budget_chars=100,
        voice_page_size=1,
    )

    assert [row["child_id"] for row in result.sources] == [
        "skill-2",
        "voice-1",
        "skill-1",
    ]
    assert result.sources[1]["matched_intents"] == ("voice", "media")
    assert [coverage.retained for coverage in result.coverage] == [2, 1]
    assert [row["child_id"] for row in result.omitted_rows] == ["profile-1"]


def test_allocator_keeps_all_exact_skills_and_clamps_distinct_voice_text():
    bundle = packet_policy.compose_packet_policies("character", ("skill", "voice"))
    skills = [_row(f"skill-{index}", "skill", score=0.5 - index / 100) for index in range(5)]
    voices = [_row(f"voice-{index}", "voice", score=0.4 - index / 100) for index in range(4)]

    result = retrieval_budget.allocate_sources(
        [*skills, *voices],
        {"skill": skills, "voice": voices},
        bundle,
        max_sources=10,
        context_budget_chars=100,
        voice_page_size=2,
    )

    retained_ids = {row["child_id"] for row in result.sources}
    assert {row["child_id"] for row in skills} <= retained_ids
    assert len([row for row in result.sources if "voice" in row["matched_intents"]]) == 2
    assert {row["child_id"] for row in result.omitted_rows} == {"voice-2", "voice-3"}
    assert result.coverage == (
        retrieval_budget.IntentCoverage("skill", available=5, target=5, retained=5, shortfall=0),
        retrieval_budget.IntentCoverage("voice", available=4, target=2, retained=2, shortfall=0),
    )


def test_allocator_preserves_each_intent_before_completing_targets_under_budget():
    bundle = packet_policy.compose_packet_policies("character", ("skill", "voice"))
    skills = [
        _row("skill-1", "skill", score=0.9, text="aaaa"),
        _row("skill-2", "skill", score=0.8, text="bbbb"),
    ]
    voice = _row("voice-1", "voice", score=0.1, text="cccc")

    result = retrieval_budget.allocate_sources(
        [*skills, voice],
        {"skill": skills, "voice": [voice]},
        bundle,
        max_sources=2,
        context_budget_chars=8,
        voice_page_size=1,
    )

    assert [row["child_id"] for row in result.sources] == ["skill-1", "voice-1"]
    assert result.chars_used == 8
    assert result.coverage[0].shortfall == 1
    assert result.coverage[1].shortfall == 0
    assert [row["child_id"] for row in result.omitted_rows] == ["skill-2"]


def test_allocator_reports_unavailable_intent_without_borrowing_a_duplicate():
    bundle = packet_policy.compose_packet_policies("character", ("skill", "item"))
    skill = _row("shared", "skill", score=1.0)

    result = retrieval_budget.allocate_sources(
        [skill, dict(skill)],
        {"skill": [skill], "item": []},
        bundle,
        max_sources=2,
        context_budget_chars=100,
        voice_page_size=8,
    )

    assert [row["child_id"] for row in result.sources] == ["shared"]
    assert result.coverage[1] == retrieval_budget.IntentCoverage(
        "item", available=0, target=1, retained=0, shortfall=1
    )
    assert result.omitted_rows == []


def test_allocator_enforces_character_budget_and_only_omits_unique_trimmed_rows():
    bundle = packet_policy.compose_packet_policies("character", ("culture",))
    oversized = _row("too-long", "culture", score=1.0, text="123456")
    fitting = _row("fits", "culture", score=0.5, text="1234")

    result = retrieval_budget.allocate_sources(
        [oversized, fitting, dict(fitting)],
        {"culture": [oversized, fitting]},
        bundle,
        max_sources=1,
        context_budget_chars=4,
        voice_page_size=8,
    )

    assert [row["child_id"] for row in result.sources] == ["fits"]
    assert result.chars_used == 4
    assert [row["child_id"] for row in result.omitted_rows] == ["too-long"]


def test_allocator_uses_shared_child_when_it_is_the_only_physical_full_coverage():
    bundle = packet_policy.compose_packet_policies("character", ("skill", "voice"))
    skill_only = _row("skill-only", "skill", score=1.0)
    shared = {
        **_row("shared", "skill", score=0.5),
        "matched_intents": ("skill", "voice"),
    }

    result = retrieval_budget.allocate_sources(
        [skill_only, shared],
        {"skill": [shared], "voice": [shared]},
        bundle,
        max_sources=1,
        context_budget_chars=100,
        voice_page_size=1,
    )

    assert [row["child_id"] for row in result.sources] == ["shared"]
    assert [coverage.shortfall for coverage in result.coverage] == [0, 0]


def test_allocator_avoids_long_shared_row_when_separate_rows_preserve_all_intents():
    bundle = packet_policy.compose_packet_policies(
        "character", ("profile_fact", "culture", "voice")
    )
    shared_dossier = {
        **_row("dossier", score=1.0, text="12345"),
        "matched_intents": ("profile_fact", "culture"),
    }
    profile = _row("profile", "profile_fact", score=0.8, text="12")
    culture = _row("culture", "culture", score=0.7, text="34")
    voice = _row("voice", "voice", score=0.6, text="56")

    result = retrieval_budget.allocate_sources(
        [shared_dossier, profile, culture, voice],
        {
            "profile_fact": [shared_dossier, profile],
            "culture": [shared_dossier, culture],
            "voice": [voice],
        },
        bundle,
        max_sources=3,
        context_budget_chars=6,
        voice_page_size=1,
    )

    assert [row["child_id"] for row in result.sources] == ["profile", "culture", "voice"]
    assert [coverage.shortfall for coverage in result.coverage] == [0, 0, 0]
    assert result.chars_used == 6


def test_allocator_uses_short_voice_completion_to_preserve_all_exact_skills():
    bundle = packet_policy.compose_packet_policies("character", ("voice", "skill"))
    long_voice = _row("voice-long", "voice", score=1.0, text="1234")
    short_voices = [
        _row("voice-short-1", "voice", score=0.8, text="1"),
        _row("voice-short-2", "voice", score=0.7, text="2"),
    ]
    skills = [
        _row("skill-1", "skill", score=0.6, text="abc"),
        _row("skill-2", "skill", score=0.5, text="def"),
    ]

    result = retrieval_budget.allocate_sources(
        [long_voice, *short_voices, *skills],
        {"voice": [long_voice, *short_voices], "skill": skills},
        bundle,
        max_sources=4,
        context_budget_chars=8,
        voice_page_size=2,
    )

    assert {row["child_id"] for row in result.sources} == {
        "voice-short-1",
        "voice-short-2",
        "skill-1",
        "skill-2",
    }
    assert [coverage.shortfall for coverage in result.coverage] == [0, 0]
    assert result.chars_used == 8


def test_allocator_100_row_seven_intent_shortfall_is_bounded_and_deterministic():
    intents = ("skill", "voice", "profile_fact", "culture", "item", "media", "video")
    bundle = packet_policy.compose_packet_policies("character", intents)
    counts = {
        "skill": 28,
        "voice": 20,
        "profile_fact": 10,
        "culture": 10,
        "item": 10,
        "media": 10,
        "video": 10,
    }
    rows = []
    exact_rows_by_intent = {}
    row_index = 0
    for intent in intents:
        intent_rows = []
        for intent_index in range(counts[intent]):
            row = _row(
                f"{intent}-{intent_index}",
                intent,
                score=1000.0 - row_index,
                text="x" * (101 - row_index),
            )
            rows.append(row)
            intent_rows.append(row)
            row_index += 1
        exact_rows_by_intent[intent] = intent_rows
    rows.extend(
        [
            _row("spare-0", score=1.0, text="x"),
            _row("spare-1", score=0.5, text="x"),
        ]
    )
    assert len(rows) == 100

    started = time.perf_counter()
    result = retrieval_budget.allocate_sources(
        rows,
        exact_rows_by_intent,
        bundle,
        max_sources=20,
        context_budget_chars=10_000,
        voice_page_size=8,
    )
    elapsed = time.perf_counter() - started

    assert result.coverage == (
        retrieval_budget.IntentCoverage("skill", 28, 28, 7, 21),
        retrieval_budget.IntentCoverage("voice", 20, 8, 8, 0),
        retrieval_budget.IntentCoverage("profile_fact", 10, 1, 1, 0),
        retrieval_budget.IntentCoverage("culture", 10, 1, 1, 0),
        retrieval_budget.IntentCoverage("item", 10, 1, 1, 0),
        retrieval_budget.IntentCoverage("media", 10, 1, 1, 0),
        retrieval_budget.IntentCoverage("video", 10, 1, 1, 0),
    )
    assert len(result.sources) == 20
    assert elapsed < 2.0, f"allocator took {elapsed:.3f}s for 100 request-shaped rows"
