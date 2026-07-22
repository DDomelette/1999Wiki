from config.config import get_config, reset_config_for_test


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
