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
    "base_url",
    [
        "https://:443/base",
        "https://exa mple.com/base",
        "https://example.com:invalid/base",
        "https://example.com:70000/base",
        "https://[not-ipv6]/base",
        "https://example..com/base",
        "https://-example.com/base",
        "https://example-.com/base",
        "https://exa_mple.com/base",
        f"https://{'a' * 64}.example/base",
        "https://" + ".".join(["a" * 63] * 5) + "/base",
    ],
)
def test_normalize_public_media_base_rejects_malformed_http_authorities(base_url):
    with pytest.raises(ValueError):
        normalize_public_media_base(base_url)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://例子.测试/base",
        "https://[2001:db8::1]:9443/base",
        "http://127.0.0.1:9002",
        "http://localhost:9002",
    ],
)
def test_normalize_public_media_base_accepts_valid_idna_ip_and_localhost(base_url):
    assert normalize_public_media_base(base_url) == base_url


@pytest.mark.parametrize(
    "base_url",
    [
        "https://xn--fsqu00a.xn--0zwm56d/base",
        "https://example.com./base",
    ],
)
def test_normalize_public_media_base_accepts_valid_alabel_and_root_dot(base_url):
    assert normalize_public_media_base(base_url) == base_url


@pytest.mark.parametrize(
    "base_url",
    [
        "https://xn--a.com/base",
        "https://xn--abc.com/base",
        "https://example..com./base",
    ],
)
def test_normalize_public_media_base_rejects_malformed_alabels_and_empty_labels(
    base_url,
):
    with pytest.raises(ValueError):
        normalize_public_media_base(base_url)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://:443/base",
        "https://exa mple.com/base",
        "https://example..com/base",
        "https://example.com:invalid/base",
    ],
)
def test_projector_rejects_malformed_http_authorities(base_url):
    with pytest.raises(ValueError):
        build_public_media_url(
            base_url,
            "reverse1999-assets",
            "voice/en/file.ogg",
        )


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
        "portrait/\x7ffile.webp",
        "portrait/\x80file.webp",
        "portrait/\u200bfile.webp",
        "portrait/\ud800file.webp",
    ],
)
def test_build_public_media_url_rejects_unsafe_object_keys(object_key):
    with pytest.raises(ValueError):
        build_public_media_url("/media", "reverse1999-assets", object_key)


@pytest.mark.parametrize(
    "edge",
    [" ", "\x1f", "\x85", "\u200b"],
)
@pytest.mark.parametrize("side", ["leading", "trailing"])
def test_projector_rejects_component_edges_without_changing_identity(edge, side):
    decorate = (
        (lambda value: edge + value)
        if side == "leading"
        else (lambda value: value + edge)
    )
    key = decorate("portrait/file.webp")
    bucket = decorate("reverse1999-assets")
    base = decorate("/media")

    with pytest.raises(ValueError):
        build_public_media_url("/media", "reverse1999-assets", key)
    with pytest.raises(ValueError):
        build_public_media_url("/media", bucket, "portrait/file.webp")
    with pytest.raises(ValueError):
        build_public_media_url(base, "reverse1999-assets", "portrait/file.webp")


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
        "/media/\x7fprivate",
        "/media/\x80private",
        "/media/\u200bprivate",
        "/media/\ud800private",
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
    "unsafe_character",
    ["\x7f", "\x80", "\u200b", "\ud800"],
)
def test_project_media_row_omits_all_unicode_control_categories(unsafe_character):
    assert project_media_row(
        {
            "object_key": f"portrait/{unsafe_character}secret.webp",
            "url": "https://stored.example/stale.webp",
        },
        base_url="/media",
        bucket_name="reverse1999-assets",
    ) is None
    assert project_media_row(
        {
            "object_key": "portrait/safe.webp",
            "url": "https://stored.example/stale.webp",
        },
        base_url=f"/media/{unsafe_character}private",
        bucket_name="reverse1999-assets",
    ) is None


@pytest.mark.parametrize(
    "object_key",
    [
        " portrait/file.webp",
        "portrait/file.webp ",
        "\x1fportrait/file.webp",
        "portrait/file.webp\x1f",
        "\x85portrait/file.webp",
        "portrait/file.webp\x85",
        "\u200bportrait/file.webp",
        "portrait/file.webp\u200b",
    ],
)
def test_project_media_row_omits_edge_whitespace_without_trimming_key(object_key):
    source = {
        "object_key": object_key,
        "url": "https://stored.example/stale.webp",
    }

    assert project_media_row(
        source,
        base_url="/media",
        bucket_name="reverse1999-assets",
    ) is None
    assert source["object_key"] == object_key


@pytest.mark.parametrize(
    "value",
    [
        "/media/bucket/key.webp",
        "/media/bucket/key%20name.webp",
        "http://media.example.com/bucket/key.webp",
        "https://media.example.com/bucket/key.webp",
        "https://例子.测试/bucket/key.webp",
        "https://[2001:db8::1]:9443/bucket/key.webp",
        "https://xn--fsqu00a.xn--0zwm56d/bucket/key.webp",
        "https://example.com./bucket/key.webp",
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
        "/media/\x7fkey.webp",
        "/media/\x80key.webp",
        "/media/\u200bkey.webp",
        "/media/\ud800key.webp",
        "https://:443/key.webp",
        "https://exa mple.com/key.webp",
        "https://example..com/key.webp",
        "https://example.com:invalid/key.webp",
        "https://xn--a.com/key.webp",
        "https://xn--abc.com/key.webp",
        "https://example..com./key.webp",
    ],
)
def test_safe_public_media_url_rejects_unsafe_values(value):
    assert not is_safe_public_media_url(value)
