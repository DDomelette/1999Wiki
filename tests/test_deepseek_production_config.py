import copy
from pathlib import Path

import pytest
import yaml

import config.config as config_module
from config.config import get_config, reset_config_for_test
import src.rag.chain as chain_module
from src.rag.chain import RAGChain


ROOT = Path(__file__).resolve().parents[1]


def _settings_payload() -> dict:
    return yaml.safe_load(
        (ROOT / "config" / "settings.yaml").read_text(encoding="utf-8")
    )


def test_production_llm_uses_official_v4_flash_non_thinking_config(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(config_module, "load_dotenv", lambda *args, **kwargs: None)
    reset_config_for_test()

    cfg = get_config()

    assert cfg.llm.base_url == "https://api.deepseek.com"
    assert cfg.llm.model == "deepseek-v4-flash"
    assert cfg.llm.thinking == "disabled"


def test_invalid_production_thinking_mode_is_rejected(monkeypatch):
    raw = copy.deepcopy(_settings_payload())
    raw["llm"]["thinking"] = "automatic"
    monkeypatch.setattr(config_module, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(config_module.yaml, "safe_load", lambda stream: raw)
    reset_config_for_test()

    with pytest.raises(ValueError, match="llm.thinking"):
        get_config()


def test_missing_production_thinking_mode_defaults_to_disabled(monkeypatch):
    raw = copy.deepcopy(_settings_payload())
    del raw["llm"]["thinking"]
    monkeypatch.setattr(config_module, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(config_module.yaml, "safe_load", lambda stream: raw)
    reset_config_for_test()

    assert get_config().llm.thinking == "disabled"


def test_rag_chat_clients_send_explicit_non_thinking_body(monkeypatch):
    calls: list[dict] = []

    def fake_chat_openai(**kwargs):
        calls.append(kwargs)
        return object()

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setattr(config_module, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setattr(chain_module, "ChatOpenAI", fake_chat_openai)
    reset_config_for_test()
    cfg = get_config()
    cfg.llm.api_key = "test-key"
    chain = RAGChain.__new__(RAGChain)
    chain._cfg = cfg

    chain._build_llm(temperature=0)
    chain._build_llm(temperature=0.3)

    assert len(calls) == 2
    for call in calls:
        assert call["base_url"] == "https://api.deepseek.com"
        assert call["model"] == "deepseek-v4-flash"
        assert call["extra_body"] == {"thinking": {"type": "disabled"}}
    assert [call["temperature"] for call in calls] == [0, 0.3]
