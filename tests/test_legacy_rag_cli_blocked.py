from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REMOVED_PATHS = (
    ROOT / "scripts" / "extract_data.py",
    ROOT / "scripts" / "build_index.py",
    ROOT / "scripts" / "build_assets.py",
    ROOT / "src" / "assets" / "registry.py",
    ROOT / "src" / "assets" / "models.py",
    ROOT / "src" / "extraction" / "__init__.py",
)
PRODUCTION_ROOTS = (
    ROOT / "backend",
    ROOT / "src",
    ROOT / "scripts",
    ROOT / "config",
)
FORBIDDEN_TEXT = (
    "documents.jsonl",
    '"assets.jsonl"',
    "AssetRegistry",
    "build_vectorstore",
    "chunk_documents_for_index",
)


def test_legacy_rag_files_are_absent():
    assert [str(path.relative_to(ROOT)) for path in REMOVED_PATHS if path.exists()] == []


def test_production_python_has_no_legacy_rag_source_or_build_symbols():
    violations: list[str] = []
    for root in PRODUCTION_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if path.name == "cleanup_legacy_rag_p2.py":
                continue
            source = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_TEXT:
                if token in source:
                    violations.append(f"{path.relative_to(ROOT)}:{token}")
    assert violations == []


def test_vectorstore_keeps_runtime_and_shadow_build_only():
    source = (ROOT / "src" / "rag" / "vectorstore.py").read_text(encoding="utf-8")
    assert "class MilvusVectorstore" in source
    assert "def load_vectorstore" in source
    assert "def build_huiji_shadow_collection" in source
    assert "def add_documents" not in source
    assert "client.delete" not in source
