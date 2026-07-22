from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_milvus_http_port_avoids_windows_reserved_range():
    """Windows often reserves 9011-9110; publishing 9092 breaks Docker startup."""
    compose = yaml.safe_load((ROOT / "infra" / "milvus" / "docker-compose.yml").read_text(encoding="utf-8"))
    ports = compose["services"]["standalone"]["ports"]

    assert "9092:9091" not in ports
    assert "127.0.0.1:19091:9091" in ports


def test_milvus_grpc_port_stays_on_configured_endpoint():
    compose = yaml.safe_load((ROOT / "infra" / "milvus" / "docker-compose.yml").read_text(encoding="utf-8"))
    ports = compose["services"]["standalone"]["ports"]

    assert "127.0.0.1:19600:19530" in ports
