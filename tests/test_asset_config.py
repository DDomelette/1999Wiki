from config.config import get_config, reset_config_for_test

import pytest


def test_asset_storage_config_uses_yaml_and_env(monkeypatch):
    monkeypatch.setenv("MINIO_ACCESS_KEY", "test-user")
    monkeypatch.setenv("MINIO_SECRET_KEY", "test-secret")
    reset_config_for_test()

    cfg = get_config()

    assert cfg.assets.provider == "minio"
    assert cfg.assets.endpoint == "127.0.0.1:9002"
    assert cfg.assets.public_base_url == "http://127.0.0.1:9002"
    assert cfg.assets.bucket_name == "reverse1999-assets"
    assert cfg.assets.secure is False
    assert cfg.assets.access_key == "test-user"
    assert cfg.assets.secret_key == "test-secret"


def test_asset_storage_credentials_empty_when_env_unset(monkeypatch):
    monkeypatch.delenv("MINIO_ACCESS_KEY", raising=False)
    monkeypatch.delenv("MINIO_SECRET_KEY", raising=False)
    reset_config_for_test()

    cfg = get_config()

    assert cfg.assets.access_key == ""
    assert cfg.assets.secret_key == ""


def test_asset_storage_config_accepts_minio_root_credentials(monkeypatch):
    monkeypatch.delenv("MINIO_ACCESS_KEY", raising=False)
    monkeypatch.delenv("MINIO_SECRET_KEY", raising=False)
    monkeypatch.setenv("MINIO_ROOT_USER", "root-user")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "root-password")
    reset_config_for_test()

    cfg = get_config()

    assert cfg.assets.access_key == "root-user"
    assert cfg.assets.secret_key == "root-password"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("MINIO_SECURE", "perhaps"),
        ("MEDIA_PUBLIC_BASE_URL", "ftp://media.example.com"),
        ("MEDIA_PUBLIC_BASE_URL", "/media/../secret"),
        ("MEDIA_PUBLIC_BASE_URL", "https://user:pass@example.com/media"),
        ("MEDIA_PUBLIC_BASE_URL", "/media?token=value"),
    ],
)
def test_runtime_asset_environment_rejects_unsafe_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    reset_config_for_test()

    with pytest.raises(ValueError, match=name) as error:
        get_config()

    assert value not in str(error.value)
