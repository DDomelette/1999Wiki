"""Deterministic, collision-resistant inventory for a MySQL schema."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Protocol, Sequence


INVENTORY_SCHEMA = "huiji.wiki-mysql-inventory/v1"


class MysqlQueryClient(Protocol):
    def query_bytes(self, sql: str, *, database: str | None = None) -> bytes: ...


def quote_mysql_identifier(value: str) -> str:
    if "\x00" in value:
        raise ValueError("MySQL identifier contains NUL")
    return "`" + value.replace("`", "``") + "`"


def encode_canonical_cell(type_name: str, hex_value: str | None, *, is_null: bool) -> bytes:
    if is_null:
        return b"N;"
    if hex_value is None:
        raise ValueError("non-null canonical cell requires hex bytes")
    normalized = hex_value.upper()
    if len(normalized) % 2 or any(char not in "0123456789ABCDEF" for char in normalized):
        raise ValueError("canonical cell has invalid hex bytes")
    encoded_type = type_name.encode("utf-8")
    byte_length = len(normalized) // 2
    return (
        b"V"
        + str(len(encoded_type)).encode("ascii")
        + b":"
        + encoded_type
        + str(byte_length).encode("ascii")
        + b":"
        + normalized.encode("ascii")
        + b";"
    )


def hash_encoded_rows(rows: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(len(row).to_bytes(8, "big"))
        digest.update(row)
    return digest.hexdigest()


def build_table_digest_sql(
    table_name: str,
    columns: Sequence[dict[str, Any]],
    primary_key: Sequence[str],
) -> str:
    if not columns:
        raise ValueError(f"table has no columns: {table_name}")
    if not primary_key:
        raise ValueError(f"table has no primary key: {table_name}")
    known = {str(column["name"]) for column in columns}
    if any(name not in known for name in primary_key):
        raise ValueError(f"primary key references unknown column: {table_name}")
    cells: list[str] = []
    for column in columns:
        name = quote_mysql_identifier(str(column["name"]))
        type_name = str(column["type"])
        type_literal = _sql_string(type_name)
        type_length = len(type_name.encode("utf-8"))
        cells.append(
            "IF("
            f"{name} IS NULL,'N;',"
            "CONCAT('V',"
            f"'{type_length}:',{type_literal},"
            f"OCTET_LENGTH(CAST({name} AS BINARY)),':',"
            f"HEX(CAST({name} AS BINARY)),';'))"
        )
    order = ", ".join(f"{quote_mysql_identifier(name)} ASC" for name in primary_key)
    return (
        f"SELECT CONCAT({','.join(cells)}) "
        f"FROM {quote_mysql_identifier(table_name)} ORDER BY {order};"
    )


def collect_mysql_inventory(client: MysqlQueryClient, database: str) -> dict[str, Any]:
    table_rows = _rows(
        client.query_bytes(
            "SELECT HEX(TABLE_NAME),HEX(COALESCE(ENGINE,'')) "
            "FROM information_schema.TABLES "
            f"WHERE TABLE_SCHEMA={_sql_string(database)} AND TABLE_TYPE='BASE TABLE' "
            "ORDER BY TABLE_NAME;"
        )
    )
    tables: list[dict[str, Any]] = []
    seen: set[str] = set()
    for fields in table_rows:
        if len(fields) != 2:
            raise ValueError("invalid table metadata row")
        name = _from_hex(fields[0])
        if name in seen:
            raise ValueError(f"duplicate table name: {name}")
        seen.add(name)
        engine = _from_hex(fields[1])
        columns = _load_columns(client, database, name)
        primary_key = _load_primary_key(client, database, name)
        if not primary_key:
            raise ValueError(f"table has no primary key: {name}")
        row_count = _single_int(
            client.query_bytes(
                f"SELECT COUNT(*) FROM {quote_mysql_identifier(name)};",
                database=database,
            )
        )
        digest_sql = build_table_digest_sql(name, columns, primary_key)
        data_output = client.query_bytes(digest_sql, database=database)
        encoded_rows = [line for line in data_output.splitlines()]
        if len(encoded_rows) != row_count:
            raise ValueError(
                f"canonical row stream count mismatch for {name}: {len(encoded_rows)} != {row_count}"
            )
        ddl_bytes = client.query_bytes(
            f"SHOW CREATE TABLE {quote_mysql_identifier(name)};",
            database=database,
        )
        ddl_identity = {
            "engine": engine,
            "columns": columns,
            "primary_key": primary_key,
        }
        tables.append({
            "name": name,
            "engine": engine,
            "columns": columns,
            "primary_key": primary_key,
            "row_count": row_count,
            "ddl_sha256": hashlib.sha256(_canonical_json(ddl_identity)).hexdigest(),
            "show_create_sha256": hashlib.sha256(ddl_bytes).hexdigest(),
            "data_sha256": hash_encoded_rows(encoded_rows),
        })
    tables.sort(key=lambda item: item["name"])
    installed_snapshot = _load_installed_snapshot(client, database, seen)
    identity = {
        "schema_version": INVENTORY_SCHEMA,
        "database": database,
        "tables": tables,
        "installed_snapshot": installed_snapshot,
    }
    hash_identity = {
        **identity,
        "tables": [
            {key: value for key, value in table.items() if key != "show_create_sha256"}
            for table in tables
        ],
    }
    identity["inventory_sha256"] = hashlib.sha256(_canonical_json(hash_identity)).hexdigest()
    return identity


def compare_inventories(source: dict[str, Any], restored: dict[str, Any]) -> list[str]:
    differences: list[str] = []
    left = {str(item["name"]): item for item in source.get("tables", [])}
    right = {str(item["name"]): item for item in restored.get("tables", [])}
    if set(left) != set(right):
        differences.append(f"table_set: {sorted(left)} != {sorted(right)}")
    for name in sorted(set(left) & set(right)):
        for field in ("engine", "columns", "primary_key", "ddl_sha256", "row_count", "data_sha256"):
            if left[name].get(field) != right[name].get(field):
                differences.append(
                    f"{name}.{field}: {left[name].get(field)!r} != {right[name].get(field)!r}"
                )
    if source.get("installed_snapshot") != restored.get("installed_snapshot"):
        differences.append("installed_snapshot differs")
    if source.get("inventory_sha256") != restored.get("inventory_sha256"):
        differences.append("inventory_sha256 differs")
    return differences


def _load_columns(client: MysqlQueryClient, database: str, table: str) -> list[dict[str, Any]]:
    sql = (
        "SELECT HEX(COLUMN_NAME),HEX(COLUMN_TYPE),ORDINAL_POSITION,"
        "HEX(IS_NULLABLE),(COLUMN_DEFAULT IS NULL),"
        "HEX(COALESCE(COLUMN_DEFAULT,'')),HEX(COALESCE(EXTRA,'')),"
        "HEX(COALESCE(COLLATION_NAME,'')),HEX(DATA_TYPE) "
        "FROM information_schema.COLUMNS "
        f"WHERE TABLE_SCHEMA={_sql_string(database)} AND TABLE_NAME={_sql_string(table)} "
        "ORDER BY ORDINAL_POSITION;"
    )
    result: list[dict[str, Any]] = []
    for fields in _rows(client.query_bytes(sql)):
        if len(fields) != 9:
            raise ValueError(f"invalid column metadata row for {table}")
        result.append({
            "name": _from_hex(fields[0]),
            "type": _from_hex(fields[1]),
            "ordinal": int(fields[2]),
            "nullable": _from_hex(fields[3]),
            "default_is_null": fields[4] == "1",
            "default": _from_hex(fields[5]),
            "extra": _from_hex(fields[6]),
            "collation": _from_hex(fields[7]),
            "data_type": _from_hex(fields[8]),
        })
    return result


def _load_primary_key(client: MysqlQueryClient, database: str, table: str) -> list[str]:
    sql = (
        "SELECT HEX(COLUMN_NAME) FROM information_schema.KEY_COLUMN_USAGE "
        f"WHERE TABLE_SCHEMA={_sql_string(database)} AND TABLE_NAME={_sql_string(table)} "
        "AND CONSTRAINT_NAME='PRIMARY' ORDER BY ORDINAL_POSITION;"
    )
    return [_from_hex(fields[0]) for fields in _rows(client.query_bytes(sql))]


def _load_installed_snapshot(
    client: MysqlQueryClient,
    database: str,
    table_names: set[str],
) -> dict[str, Any]:
    if "wiki_import_snapshots" not in table_names:
        raise ValueError("wiki_import_snapshots table is missing")
    sql = (
        "SELECT HEX(CAST(source_mode AS BINARY)),HEX(CAST(build_version AS BINARY)),"
        "HEX(CAST(artifact_schema_version AS BINARY)),"
        "HEX(CAST(manifest_sha256 AS BINARY)),HEX(CAST(snapshot_sha256 AS BINARY)) "
        "FROM wiki_import_snapshots ORDER BY id;"
    )
    rows = _rows(client.query_bytes(sql, database=database))
    if len(rows) != 1 or len(rows[0]) != 5:
        raise ValueError("wiki_import_snapshots must contain exactly one valid row")
    values = [_from_hex(value) for value in rows[0]]
    return dict(zip(
        ("source_mode", "build_version", "artifact_schema_version", "manifest_sha256", "snapshot_sha256"),
        values,
        strict=True,
    ))


def _rows(payload: bytes) -> list[list[str]]:
    if not payload:
        return []
    return [line.decode("ascii").split("\t") for line in payload.splitlines()]


def _single_int(payload: bytes) -> int:
    rows = _rows(payload)
    if len(rows) != 1 or len(rows[0]) != 1:
        raise ValueError("expected one integer result")
    return int(rows[0][0])


def _from_hex(value: str) -> str:
    try:
        return bytes.fromhex(value).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("invalid UTF-8 hex metadata") from exc


def _sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
