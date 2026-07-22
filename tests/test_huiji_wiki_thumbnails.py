import pytest

from src.huiji_wiki.thumbnails import build_thumbnail_plan, refuse_thumbnail_collision, validate_apply_confirmation


def test_thumbnail_plan_is_deterministic_deduplicated_and_isolated():
    rows = [
        {"media_id": "m1", "asset_type": "portrait", "url": "http://minio/source.webp"},
        {"media_id": "m1", "asset_type": "portrait", "url": "http://minio/source.webp"},
        {"media_id": "voice", "asset_type": "voice", "url": "http://minio/voice.mp3"},
    ]
    first = build_thumbnail_plan(rows, "http://127.0.0.1:9002", "reverse1999-assets")
    second = build_thumbnail_plan(rows, "http://127.0.0.1:9002", "reverse1999-assets")

    assert first == second
    assert len(first["entries"]) == 1
    entry = first["entries"][0]
    assert entry["thumbnailObjectKey"].startswith("reverse1999/wiki-thumbnail/")
    assert entry["thumbnailUrl"].startswith("http://127.0.0.1:9002/reverse1999-assets/")
    assert first["mode"] == "dry-run"


def test_apply_requires_exact_prefix_and_refuses_existing_objects():
    with pytest.raises(ValueError):
        validate_apply_confirmation(True, "reverse1999/")
    validate_apply_confirmation(True, "reverse1999/wiki-thumbnail/")

    class ExistingClient:
        def stat_object(self, _bucket, _key):
            return object()

    with pytest.raises(RuntimeError, match="collision refused"):
        refuse_thumbnail_collision(ExistingClient(), "bucket", "reverse1999/wiki-thumbnail/a.webp")
