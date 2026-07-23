import copy
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config.config as config_module
from config.config import get_config, reset_config_for_test
from src.huijiwiki.project_paths import ProjectPathViolation


ROOT = Path(__file__).resolve().parents[1]


def _settings_payload() -> dict:
    return yaml.safe_load((ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))


def test_config_loads_basic_fields():
    reset_config_for_test()
    cfg = get_config()
    settings = _settings_payload()
    assert cfg.embedding.model == "BAAI/bge-m3"
    assert cfg.vectorstore.provider == "milvus"
    assert cfg.vectorstore.db_name == "reverse1999_rag"
    assert cfg.vectorstore.collection_name == settings["vectorstore"]["collection_name"]
    assert cfg.rag.chunk_size == 500
    assert cfg.server.backend_port == 8000
    assert cfg.paths.project_root.exists()
    assert not hasattr(cfg.paths, "data_raw")
    assert not hasattr(cfg.paths, "data_processed")


def test_route_and_reranker_config_defaults(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    reset_config_for_test()
    cfg = get_config()
    settings = _settings_payload()
    assert cfg.huiji.text_collection_name == settings["huiji"]["text_collection_name"]
    assert cfg.huiji.source_mode == "huiji_crawler"
    assert cfg.huiji.credential_file == (
        cfg.paths.project_root / ".local" / "huiji" / "credentials" / "config.dat"
    ).resolve()
    assert not hasattr(cfg, "obsidian")
    assert "obsidian" not in _settings_payload()
    assert cfg.huiji.provenance_baseline == (
        cfg.paths.project_root / "config" / "provenance" / "huiji-dev.v1.json"
    )
    assert cfg.vectorstore.collection_name == settings["vectorstore"]["collection_name"]
    assert cfg.huiji.text_collection_name == cfg.vectorstore.collection_name
    assert cfg.reranker.enabled is False
    assert cfg.reranker.model == "BAAI/bge-reranker-v2-m3"
    assert cfg.retrieval.bm25_k == 40
    assert cfg.retrieval.dense_k == 40
    assert cfg.retrieval.rerank_k == 60
    assert cfg.retrieval.candidate_oversample == 4
    assert cfg.retrieval.candidate_k_max == 100
    assert cfg.retrieval.voice_page_size == 8
    assert cfg.retrieval.voice_page_size_max == 20


def test_env_overrides_api_keys(monkeypatch):
    reset_config_for_test()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-123")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-embed-test")
    cfg = get_config()
    assert cfg.llm.api_key == "sk-test-123"
    assert cfg.embedding.api_key == "sk-embed-test"


def test_runtime_service_environment_overrides(monkeypatch):
    monkeypatch.setenv("MILVUS_URI", "http://standalone:19530")
    monkeypatch.setenv("MILVUS_DB_NAME", "reverse1999_rag")
    monkeypatch.setenv("MILVUS_COLLECTION_NAME", "prod_collection")
    monkeypatch.setenv("MINIO_ENDPOINT", "minio:9000")
    monkeypatch.setenv("MINIO_SECURE", "false")
    monkeypatch.setenv("MINIO_BUCKET", "reverse1999-assets")
    monkeypatch.setenv("MEDIA_PUBLIC_BASE_URL", "/media")
    monkeypatch.setenv("HUIJI_PROCESSED_ROOT", "/runtime/rag/huiji")
    reset_config_for_test()

    cfg = get_config()

    assert cfg.vectorstore.uri == "http://standalone:19530"
    assert cfg.vectorstore.db_name == "reverse1999_rag"
    assert cfg.vectorstore.collection_name == "prod_collection"
    assert cfg.assets.endpoint == "minio:9000"
    assert cfg.assets.secure is False
    assert cfg.assets.bucket_name == "reverse1999-assets"
    assert cfg.assets.public_base_url == "/media"
    assert cfg.huiji.processed_root == Path("/runtime/rag/huiji")


def test_api_keys_empty_when_env_unset(monkeypatch):
    reset_config_for_test()
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    monkeypatch.setattr(config_module, "load_dotenv", lambda *a, **k: None)
    cfg = get_config()
    assert cfg.llm.api_key == ""
    assert cfg.embedding.api_key == ""


def test_huiji_credential_env_override_wins_over_settings(monkeypatch):
    override = ROOT / ".local" / "huiji" / "credentials" / "override.dat"
    monkeypatch.setenv("HUIJI_CONFIG_PATH", str(override))
    reset_config_for_test()

    cfg = get_config()

    assert cfg.huiji.credential_file == override.resolve()


def test_huiji_credential_env_override_cannot_escape_project(monkeypatch, tmp_path):
    monkeypatch.setenv("HUIJI_CONFIG_PATH", str(tmp_path / "outside.dat"))
    reset_config_for_test()

    with pytest.raises(ProjectPathViolation, match="HUIJI_CONFIG_PATH"):
        get_config()


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("raw_root", "../outside-raw"),
        ("processed_root", "../outside-processed"),
        ("provenance_baseline", "../outside-baseline.json"),
    ],
)
def test_huiji_project_data_paths_reject_parent_escape(monkeypatch, field, bad_value):
    raw = copy.deepcopy(_settings_payload())
    raw["huiji"][field] = bad_value
    monkeypatch.delenv("HUIJI_CONFIG_PATH", raising=False)
    monkeypatch.setattr(config_module, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(config_module.yaml, "safe_load", lambda stream: raw)
    reset_config_for_test()

    with pytest.raises(ProjectPathViolation, match=field):
        get_config()


@pytest.mark.parametrize("field", ["raw_root", "processed_root", "provenance_baseline"])
def test_huiji_project_data_paths_reject_external_absolute_path(monkeypatch, tmp_path, field):
    raw = copy.deepcopy(_settings_payload())
    raw["huiji"][field] = str(tmp_path / field)
    monkeypatch.delenv("HUIJI_CONFIG_PATH", raising=False)
    monkeypatch.setattr(config_module, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(config_module.yaml, "safe_load", lambda stream: raw)
    reset_config_for_test()

    with pytest.raises(ProjectPathViolation, match=field):
        get_config()
