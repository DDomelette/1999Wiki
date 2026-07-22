from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[1]


def test_legacy_obsidian_wiki_runtime_entry_points_are_removed():
    legacy_paths = [
        "src/huiji_wiki/raw_character_enrichment.py",
        "src/huiji_wiki/supplement_media.py",
        "scripts/enrich_wiki_from_raw.py",
        "scripts/import_wiki_roster_avatars.py",
        "src/extraction/obsidian_extractor.py",
        "src/assets/extractor.py",
    ]

    assert [path for path in legacy_paths if (PROJECT_ROOT / path).exists()] == []


def test_public_wiki_contract_has_no_supplement_runtime_fields():
    contract_paths = [
        "src/huiji_wiki/repository.py",
        "backend/wiki_schemas.py",
        "frontend/react-app/src/types/wiki.ts",
        "frontend/react-app/src/components/wiki/WikiShell.tsx",
    ]

    violations: list[str] = []
    for relative_path in contract_paths:
        text = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8").casefold()
        if "supplement" in text or "obsidian" in text or "wiki-supplement" in text:
            violations.append(relative_path)

    assert violations == []


def test_legacy_asset_cli_is_removed():
    assert not (PROJECT_ROOT / "scripts/build_assets.py").exists()
