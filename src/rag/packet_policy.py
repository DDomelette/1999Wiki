from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PacketPolicy:
    name: str
    sections: tuple[str, ...]
    output_mode: str
    panel: str = ""
    auto_media_types: tuple[str, ...] = ()
    intent_media_types: tuple[str, ...] = ()
    omitted_parent_actions: bool = False
    context_budget_chars: int = 9000
    coverage_mode: str = "at_least_one"
    source_target: int = 1


def _ordered_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    unique: list[str] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return tuple(unique)


@dataclass(frozen=True)
class IntentPolicyBundle:
    requested_intents: tuple[str, ...]
    policies: tuple[PacketPolicy, ...]
    sections: tuple[str, ...]
    media_types: tuple[str, ...]
    context_budget_chars: int

    @property
    def expansion_policy(self) -> PacketPolicy:
        return PacketPolicy(
            name="composite",
            sections=self.sections,
            output_mode=self.policies[0].output_mode if self.policies else "rag",
            auto_media_types=self.media_types,
            omitted_parent_actions=any(policy.omitted_parent_actions for policy in self.policies),
            context_budget_chars=self.context_budget_chars,
        )


CHARACTER_POLICIES: dict[str, PacketPolicy] = {
    "intro": PacketPolicy(
        name="intro_full",
        sections=(
            "dossier",
            "profile",
            "collection",
            "culture_dossier",
            "skills",
            "media",
            "udimo",
        ),
        output_mode="encyclopedia_summary",
        auto_media_types=("portrait", "image"),
        omitted_parent_actions=True,
    ),
    "profile": PacketPolicy(
        name="profile_fact",
        sections=("profile", "dossier"),
        output_mode="fact_answer",
        auto_media_types=("portrait",),
    ),
    "profile_fact": PacketPolicy(
        name="profile_fact",
        sections=("profile", "dossier"),
        output_mode="fact_answer",
        auto_media_types=("portrait",),
    ),
    "skill": PacketPolicy(
        name="section_detail",
        sections=("skills",),
        output_mode="section_detail",
        auto_media_types=("skill",),
        coverage_mode="all_available",
    ),
    "item": PacketPolicy(
        name="section_detail",
        sections=("collection",),
        output_mode="section_detail",
        auto_media_types=("image",),
    ),
    "culture": PacketPolicy(
        name="section_detail",
        sections=("culture_dossier",),
        output_mode="section_detail",
        auto_media_types=("image",),
    ),
    "udimo": PacketPolicy(
        name="section_detail",
        sections=("udimo",),
        output_mode="section_detail",
        auto_media_types=("image",),
    ),
    "media": PacketPolicy(
        name="media_detail",
        sections=("media", "skins", "profile"),
        output_mode="media_detail",
        auto_media_types=("portrait", "image"),
    ),
    "voice": PacketPolicy(
        name="voice_detail",
        sections=("voice",),
        output_mode="panel",
        panel="voice",
        intent_media_types=("voice",),
        coverage_mode="fixed",
        source_target=8,
    ),
    "video": PacketPolicy(
        name="video_detail",
        sections=("media",),
        output_mode="panel",
        panel="video",
        intent_media_types=("video",),
    ),
}


_LEGACY_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "intro": ("culture", "items", "item"),
    # The installed legacy projection used the two names in reverse.
    "item": ("culture",),
    "culture": ("items", "item"),
}


def get_packet_policy(
    entity_type: str | None,
    intent: str,
    artifact_capability: str = "v3",
) -> PacketPolicy:
    if entity_type == "character":
        policy = CHARACTER_POLICIES.get(intent, CHARACTER_POLICIES["intro"])
        if artifact_capability in {"legacy", "v2"}:
            aliases = _LEGACY_SECTION_ALIASES.get(intent, ())
            if aliases:
                return PacketPolicy(
                    name=policy.name,
                    sections=_ordered_unique((*policy.sections, *aliases)),
                    output_mode=policy.output_mode,
                    panel=policy.panel,
                    auto_media_types=policy.auto_media_types,
                    intent_media_types=policy.intent_media_types,
                    omitted_parent_actions=policy.omitted_parent_actions,
                    context_budget_chars=policy.context_budget_chars,
                    coverage_mode=policy.coverage_mode,
                    source_target=policy.source_target,
                )
        return policy
    return PacketPolicy(name="default", sections=(), output_mode="rag")


def compose_packet_policies(
    entity_type: str | None,
    intents: tuple[str, ...],
    artifact_capability: str = "v3",
) -> IntentPolicyBundle:
    requested_intents = _ordered_unique(intents)
    policies = tuple(
        get_packet_policy(entity_type, intent, artifact_capability)
        for intent in requested_intents
    )
    sections = _ordered_unique(tuple(section for policy in policies for section in policy.sections))
    media_types = _ordered_unique(
        tuple(
            media_type
            for policy in policies
            for media_type in (*policy.auto_media_types, *policy.intent_media_types)
        )
    )
    context_budget_chars = min(
        (policy.context_budget_chars for policy in policies),
        default=9000,
    )
    return IntentPolicyBundle(
        requested_intents=requested_intents,
        policies=policies,
        sections=sections,
        media_types=media_types,
        context_budget_chars=context_budget_chars,
    )
