from __future__ import annotations

import pytest

from src.assets.public_url import (
    build_public_media_url,
    is_safe_public_media_url,
    normalize_public_media_base,
    project_media_row,
)


def test_build_public_media_url_encodes_components_and_preserves_key_separators():
    assert build_public_media_url(
        "/media",
        "reverse1999 assets",
        "reverse1999/portrait/角色 图.webp",
    ) == (
        "/media/reverse1999%20assets/"
        "reverse1999/portrait/%E8%A7%92%E8%89%B2%20%E5%9B%BE.webp"
    )


def test_build_public_media_url_supports_absolute_https_base():
    assert build_public_media_url(
        "https://media.example.com/base",
        "reverse1999-assets",
        "voice/en/file.ogg",
    ) == "https://media.example.com/base/reverse1999-assets/voice/en/file.ogg"


@pytest.mark.parametrize(
    "object_key",
    [
        "",
        " ",
        "/portrait/file.webp",
        "portrait/../file.webp",
        "portrait/./file.webp",
        "portrait/%2e%2e/file.webp",
        "portrait/%252e%252e/file.webp",
        r"portrait\file.webp",
        "portrait/file.webp?token=secret",
        "portrait/file.webp#fragment",
        "portrait/\x00file.webp",
        "portrait/\x1ffile.webp",
    ],
)
def test_build_public_media_url_rejects_unsafe_object_keys(object_key):
    with pytest.raises(ValueError):
        build_public_media_url("/media", "reverse1999-assets", object_key)


@pytest.mark.parametrize(
    "bucket_name",
    [
        "",
        " ",
        "/bucket",
        "bucket/name",
        ".",
        "..",
        "%2e%2e",
        r"bucket\name",
        "bucket?token",
        "bucket#fragment",
        "bucket\x00name",
    ],
)
def test_build_public_media_url_rejects_unsafe_bucket_names(bucket_name):
    with pytest.raises(ValueError):
        build_public_media_url("/media", bucket_name, "portrait/file.webp")


@pytest.mark.parametrize(
    "base_url",
    [
        "",
        "//media.example.com",
        "///media.example.com",
        "ftp://media.example.com",
        "https://user:pass@media.example.com/base",
        "/media?token=value",
        "/media#fragment",
        "/media/../secret",
        "/media/%2e%2e/secret",
        "/media/%252e%252e/secret",
        r"/media\private",
        "/media/\x00private",
    ],
)
def test_normalize_public_media_base_rejects_unsafe_values(base_url):
    with pytest.raises(ValueError):
        normalize_public_media_base(base_url)


def test_project_media_row_replaces_untrusted_stored_url_from_object_key():
    source = {
        "media_id": "m1",
        "object_key": "reverse1999/portrait/stale.webp",
        "url": (
            "http://127.0.0.1:9002/"
            "reverse1999-assets/reverse1999/portrait/stale.webp"
        ),
    }

    projected = project_media_row(
        source,
        base_url="/media",
        bucket_name="reverse1999-assets",
    )

    assert projected == {
        **source,
        "url": "/media/reverse1999-assets/reverse1999/portrait/stale.webp",
    }
    assert source["url"].startswith("http://127.0.0.1:9002/")


@pytest.mark.parametrize(
    "object_key",
    [None, "", "../secret.webp", r"portrait\secret.webp"],
)
def test_project_media_row_omits_missing_or_unsafe_object_keys(object_key):
    assert project_media_row(
        {"object_key": object_key, "url": "https://stored.example/stale.webp"},
        base_url="/media",
        bucket_name="reverse1999-assets",
    ) is None


@pytest.mark.parametrize(
    "value",
    [
        "/media/bucket/key.webp",
        "/media/bucket/key%20name.webp",
        "http://media.example.com/bucket/key.webp",
        "https://media.example.com/bucket/key.webp",
    ],
)
def test_safe_public_media_url_accepts_same_origin_paths_and_http_urls(value):
    assert is_safe_public_media_url(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "relative/key.webp",
        "//media.example.com/key.webp",
        "ftp://media.example.com/key.webp",
        "https://user:pass@media.example.com/key.webp",
        "/media/../key.webp",
        "/media/%2e%2e/key.webp",
        r"/media\key.webp",
        "/media/key.webp?token=value",
        "/media/key.webp#fragment",
        "/media/\x00key.webp",
    ],
)
def test_safe_public_media_url_rejects_unsafe_values(value):
    assert not is_safe_public_media_url(value)
