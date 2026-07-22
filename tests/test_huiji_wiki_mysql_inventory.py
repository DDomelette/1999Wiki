from __future__ import annotations

import hashlib

import pytest

from src.huiji_wiki.mysql_inventory import (
    build_table_digest_sql,
    compare_inventories,
    encode_canonical_cell,
    hash_encoded_rows,
    quote_mysql_identifier,
)


def test_cell_encoding_distinguishes_null_text_and_control_bytes():
    null = encode_canonical_cell("varchar(20)", None, is_null=True)
    text_null = encode_canonical_cell("varchar(20)", "4E554C4C", is_null=False)
    controls = encode_canonical_cell("blob", "00090A5C", is_null=False)

    assert null != text_null
    assert controls != text_null
    assert null == b"N;"
    assert b"00090A5C" in controls


def test_hash_rows_is_length_prefixed_and_order_sensitive():
    rows = [b"a\tb", b"a", b"b"]

    digest = hash_encoded_rows(rows)

    expected = hashlib.sha256()
    for row in rows:
        expected.update(len(row).to_bytes(8, "big"))
        expected.update(row)
    assert digest == expected.hexdigest()
    assert digest != hash_encoded_rows(reversed(rows))


def test_digest_sql_uses_hex_projection_and_composite_primary_key_order():
    sql = build_table_digest_sql(
        "wiki`pages",
        [
            {"name": "page_id", "type": "varchar(255)"},
            {"name": "body", "type": "longtext"},
        ],
        ["page_id", "body"],
    )

    assert "HEX(CAST(`page_id` AS BINARY))" in sql
    assert "HEX(CAST(`body` AS BINARY))" in sql
    assert "ORDER BY `page_id` ASC, `body` ASC" in sql
    assert "`wiki``pages`" in sql


def test_identifier_rejects_nul_and_quotes_backticks():
    assert quote_mysql_identifier("a`b") == "`a``b`"
    with pytest.raises(ValueError, match="NUL"):
        quote_mysql_identifier("bad\x00name")


def test_compare_inventory_reports_table_and_digest_differences():
    source = {
        "schema_version": "huiji.wiki-mysql-inventory/v1",
        "inventory_sha256": "a" * 64,
        "tables": [{"name": "wiki_pages", "row_count": 1, "data_sha256": "b" * 64}],
    }
    restored = {
        **source,
        "inventory_sha256": "c" * 64,
        "tables": [{"name": "wiki_pages", "row_count": 2, "data_sha256": "d" * 64}],
    }

    differences = compare_inventories(source, restored)

    assert any("row_count" in item for item in differences)
    assert any("data_sha256" in item for item in differences)

