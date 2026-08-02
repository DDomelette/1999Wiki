from __future__ import annotations

import base64
import builtins
import copy
import errno
import hashlib
import importlib
import importlib.util
import io
import json
import os
import platform
import socket
import subprocess
import zlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest


SCRIPT_RELATIVE_PATH = "scripts/diagnose_huiji_corpus_fidelity.py"
SCRIPT = Path(__file__).resolve().parents[1] / SCRIPT_RELATIVE_PATH
HEAD = "11f038a2c479f1383dfcac7b4bb7d9f4e6710e01"
TREE = "7d0adb73ec194f8f20675720935c61e3baa5724b"
C8A_COMMIT = "012c7ca6b3abaa0445ccd00a8974ea4fefcbd333"
C8B_COMMIT = "7366787401603e9a86d7277c99b3cc3f49e97508"
C8C_COMMIT = "9c226de2e850ecabf8e672afaacc8a517e802e7d"
DESCENDANT_HEAD = "df61f8bcc7316a951bf1dad6ad9c475a5ac91994"
DESCENDANT_TREE = "3c4fdc97e6addd88999e237b47930425d998291a"
C8B_RECEIPT_SHA256 = (
    "7dfc5cce2fda7b1b7ce97f76e59413a16c8df249abe1d1aa891b32892646fc20"
)
C8C_RECEIPT_SHA256 = (
    "55d9f63504b1522c250e049bd2fbaff66db70cab382030baf4b35bfe87cb8df2"
)
C8B_TAXONOMY_SHA256 = (
    "44a511ba41a7067e4536c51226c8c40603c55806653a22bde468be066ac32ecd"
)
C8B_EVIDENCE_MANIFEST_SHA256 = (
    "977cde250ec88e970150ce98d97339f17555639dbcf905154ffd4c9a283e5fc0"
)
C8C_PRODUCT_MANIFEST_SHA256 = (
    "dc7dc31936c8e85d6c6f3af5a10c1eeb9a70300ac9990476d8f27bb1b164e764"
)
PROTECTED_STATE_SHA256 = (
    "ef85f54d229e05d975092badfd734899e85c6a74d30f0cac310b8b0d0a4b355f"
)
RUN_ID = "task8-c-c8d-fixture-20260731T000000Z"
SCRIPT_BYTES = SCRIPT.read_bytes()
SCRIPT_SHA256 = hashlib.sha256(SCRIPT_BYTES).hexdigest()
OUTPUT_NAMES = (
    "manifest.c8d-fidelity.v1.json",
    "receipt.c8d-fidelity.v1.json",
    "summary.c8d-fidelity.v1.json",
)
OUTPUT_SCHEMAS = {
    "manifest.c8d-fidelity.v1.json": "huiji.c8d-fidelity-manifest/v1",
    "receipt.c8d-fidelity.v1.json": "huiji.c8d-fidelity-receipt/v1",
    "summary.c8d-fidelity.v1.json": "huiji.c8d-fidelity-summary/v1",
}
CRAWLER_SOURCES = (
    "pages.jsonl",
    "wikitext.jsonl",
    "data_pages.jsonl",
    "resources_manifest.jsonl",
)
MEDIA_COUNTS = {
    "ambiguous_binding": 2,
    "conflicting_binding": 1,
    "missing_local_bytes": 3,
    "missing_resource_metadata": 0,
    "preserved_binding": 0,
    "rekeyed_binding": 0,
    "source_removed_with_evidence": 0,
}
ACTIVITY_COUNTERS = {
    "activation": 0,
    "active_pointer_changes": 0,
    "allowed_read_only_git_calls": 9,
    "downloads": 0,
    "forbidden_subprocess_calls": 0,
    "local_media_byte_reads": 0,
    "milvus_writes": 0,
    "minio_writes": 0,
    "mysql_writes": 0,
    "network": 0,
    "production_writes": 0,
    "total_subprocess_calls": 9,
    "vector_or_embedding_builds": 0,
    "writes_outside_exact_outputs": 0,
}
SAMPLE_FIELDS = {
    "record_kind",
    "classification",
    "reason_code",
    "active_identity_sha256",
    "candidate_identity_count",
    "candidate_identities_sha256",
    "source_evidence_count",
}
C8B_RECEIPT_DEFLATE_BASE64 = (
    "hVdZbyO5EX6fX0H4KQEsiVfz8D4FmSyQl+QlQICNgwaPotRjqbvRpHxkMf89xW7rsMeeNQxb"
    "JOv4WKz6qvT7F0JuctjBwbWPMOVu6G/uyE0YIjyvy24CF1dhFVcuBBiL6wNsHtnNbdUady5"
    "DFf6r8ctOLq4cc91axCG2aZjaMBwOXVlEzgeutMcSqiynXK2oXgn6LybuuLmjek0Z440wvy1"
    "KT8P0UCaYnX29u79n1tp/dw/d+nSQ7+8nt0Wg4zR8g1DqLWZNeB5xie5GN0Ff2h3ep1qhjA"
    "cdnPLCeeeolE0IkVJnrJbgZIIUfBRCLFZCu0UnfTtBgG4saOB33K4hcGVXzcGj22+Kyw8GMd"
    "T7UF1vwxst6W+bWXn1qrwOxq/CME0LzPW3/Iq1xm/neKOqQRFlAJOkRJBgmyQVOM9tEtSCtk"
    "rraK0JyXMQwVGqbUCfVnDHBQsq+Bs0+P1twFO3h3yBnqew2R27b12Lkdv4Y7ePm0v01uNLh"
    "REVhyY03grhIlgXrGxMFFJH7k006C00tpHSSOWlVNJGrbQHGpijHkXOF/vAWeoi7Lvy8upKW"
    "h9ZojI2SjeiiZx7b6VICvEnEbVIXkjllKIcn44rbzWXvDFUAKeN0CdXBXLJm/q3XTzmMkwv7"
    "Q9XQw/GScaEcYFrypRQimE6pNQkB1EhAHxDprVyJkrdaIy2abR3jbLScPjUH77teMztu+sl7"
    "pO0ivtGR82ZY1Fw2WjWRPAJmHGYd8xTzRzeHWHFhjMJQWiq0WOyJ3dxCHmTjyNM4/CE9brJm"
    "OB5c6ohble1EM6FO19+dei2k6t3X0UIXa3x9WEuAyuYTMohiGhAgo1KSq61w0D4hhkD3MnAk"
    "41J6ShM8iwabxLl3rKmUfFTVOPe9Z+jCvshHydYbR3G7RUKCwJTWpskEA80RgdcoT9EFHXyY"
    "HUTQEZjvQ3USVNhW8dsYJoZacMl42Mlsi51Yb7yJeO7viC+CfDviUj+0rsw9NEJRCrv76F/z"
    "Au7PCG73N+PL2WHsYLn82tf2bimS7FmbM2ak9S2K23sUmqRV8NDC8+4royKovRUEcVtX4sS"
    "j459uTqDZxdK26PCpV5nsskZaqya29NWcqhft+i88/1kvHteLE+A3JPzdRiuDVnxgaXzVn7o"
    "xnHeY2/20KrLy73xZrl0/ZYMY1l1PcGT/Sr3bsy7oZBaFDdvgNXz9nSOIXLbfkAD4RpdDhPS"
    "ZHvhQhkwHxQYzRSIhgLD5HA6KBY0ln5oqHAUgvIO/3OwNmG6OG0tDS7JZPnNGf0HD/Gma9X"
    "AXKTz8XBwSB1XSBorrGuMQ0520rqE1AsQBRXeAR76ZA0WFPcRiVJoFRO1PAXJkRpDlPZi++D"
    "6LlXOuBg3mnO0KBg46hhtpAlYmyKGQE1sGqY8TUHp4I1ChmdIUT5xJMAmcJAqhotxzJ7uEU4"
    "t75RdBlG8Fwk7ZOKzBFOUXcISXB+7iBX63hBDhjAfiL0z1lgu9FWQKwufiajNYRh/sMzx5w8"
    "03jp5o3BwBestngh/Mb2dhuN4kWdWfSK/GP6J+NCfvC8Kb0WlvNg97kv3E1HOmgtopB/Ms3"
    "cormJ6iqbknF7e5th/eFm/H8IDTBdP6lONxdFPFPoa8mvj0/CU6yhXl5UUlLDsA+nF8Hthx"
    "C/NR9JDX6bKdhEZu7xnwspV01CWCQ77aV+woZ6FBP9A6jM7OIf6LqKJFrPoNaNmKSTx1u33"
    "7f9gGlCjTEdYKOvcTyZ47OAJCRUfpd9ejVAjxc//+e8rt43szYrX1cn7V2TGw/AIkWAWoQ8"
    "k28qaHrvkA8GPQNI0HAi4sCM9PO1fqgy+TCSnhj13VIJ9FpOlL8QlBE7KDhW7KRcSXH1bUp"
    "sOmZsOwcl3QJYnf/vnr+Rp1yEXjy7AmvxjIBmHfQxlIDX6aO2W5OE4BbidGfuWDBPBgMZjKM"
    "TDzj12uBF2rseGtV74/HTLru9Kh5ReJ3zM2TZDwUSHaRrmFvsrmiWoGFdPU1fQFcGOii5I7"
    "W2kdwfICDnispC5lfyCH2cQxA/xhUyuX5Mauzzsa/Bmtb9/zUu06u3DcarJ+XoBgq5QGtUIP"
    "imG5hHI3ExnzUzyEYfJnNNxv39ZXwaG5ftJW6eRy+O+biLEjJ16HuHAlT/hHPPnOxL22Cm6"
    "9ELmLJ7d7mHrwgtZpj9ypq3zBFz7fTuD2b+0PwzlNe1OMcWeiEXTYtZhugZoD8dcpwEsb2iX"
    "seGtQj+0wYS2fhf64QCeMU96fKH6AO894fkjVg1+Q8PfuSMsdXFlqcboy/cv/wc="
)
C8C_RECEIPT_DEFLATE_BASE64 = (
    "rVdLj+M2Er7PrxD6lAXiMR+iSM2egkmAXWD3lmCBXSyEIllsMy1LAil1T08w/z1F2bKdmUmn"
    "A+Riw2Sxnl99Vf7lTVXdZXfAI3SPmHIch7t31Z1/64zbhThAvwPncJphcLh/5HfflgceXdxE"
    "T9fouzCmjhS5h2mMw9y58XiM80n+aUwPmIr0+9PBdICM62/jTieWDrY3dK5l02ija8YbJrEF"
    "03gttHZta6VzMtQttloxc/N4Triq9A0XEFomDRMNWm0ZR+ucVVYFiUJYVnsfgj89vbofe8xd"
    "PoBQDan5hS5LpKPL+7xMmKbxifKzzxPSiSDVO6Z3ot0luN/Nh4Tgd27X4z24590RfYTdlqW3"
    "R78mCgC1CtAqaINB23JywkgEpVjxByV5p6UnR1sumRB1y5G32lomKQth9bdUK7n9YYk/x45M"
    "7+0Se78P0WMf5+e303MxRWqsFkYwzUFJjk7X2NbOq+BaENgop4FxRmlqhNXMK8CmAd8Ak7Vo"
    "uH/J1Bpb9yjPppRkvEbUKEzDQJIe7kEz8tlap3mrnDEqoJUauDNcyVaxoFEZ0dZMK/eSqTER"
    "nvKcYB7T2ZxhDVOoHW8EGtW4ApCWs7q1uhaKIquNEgJrLig8b8HXVhhtmkAxgzLNZm4mvXlf"
    "PruTVTemacndZ4lkzAqnHKlnDLk0EoRmwrSWbHFrgGqonbCt8nQPRmsybRtwnrNggue/a27L"
    "YrdGilt4rQjWEU6AW45BayAMMNQQAtNA+XSUaQGNNY7ihNqhE+Qh9Yc33ILkd2Tu04prAmTf"
    "5QGmfBjnDh8pLurgK7DTMnRxxeUM+cEQdqc0+sXNuwkSJWBXIM60ZD/yluma/3cLhfy+H8Y8"
    "R3dtFmpXFagzCXbcQC19MBpb4zEodCgDgZBuPVrCiABjjTTcBMOYMzUEruCCguV4hPR8oxkt"
    "UyRIMVurOCGrBlQOW8FqIxtuLGGWc+FRWdcwV5x16BXTlEgMzQXKRxhiKPm/qvZOeyd5Kxtn"
    "CEy+cU2QEBRw0oPUoGRNkmkinZbVuvEmCOpGKk1To27qTXWiGON0q1nVVP02BMvW79YrH4j"
    "CZN14b2tqAK6E1E5xapMGavrmnlAGjWIN0dslHfgB3TIThRA8l6EQI7/cxEKxvlSUbWc9VZu"
    "YLKMbB5+LNNdvpaKcqbPIhPDQpZw7+0xgLBJGCk0fsjlLgJvjI3ajc0tKBTJX00orc5ZyMOP"
    "9SIVaL/MFVsVEwozpkfywcfBxuL96uObqAZ9/5y6PSyJ7CY9jef4U58MtcK+Cx5gzPe760R"
    "HIL6HImtdfyJA3J7VHnMHDDL/RBEcb75eRGv/qkGDNVQ1lMvSRckKqbkQMWwU+ndOxDPhh6i"
    "EO18jIuZw/yxp12IyuDJsS1ExddkmuFF/I+BTDfBHYikxT1kZPz7tSqQ0ZNJk66PvuI6aRhO"
    "e04IUJyNrgccKh2CxDPoZI9TuN7zMbjMs8LYTg0yJAw/nQweA7lygISmHAExQeoY9+e3o3Q"
    "Sa4bVgFm8d+mbGbYN5e4xpmISIHX3lyTxj2MYTT2nC9ryBQRNUKBEplNQ5Y/RvSgx+fBooN"
    "Yk+nuzyBw+oAyVeW2O6hCmk8VvMBq23wVnmGeckVieNms/QMRfQY8akYHMZuYh1tLhMn7l8"
    "rlzfRqQBrvsV22U9KZNmNU4Hk/84Xr2X4b1+Q/8oAeoX4n1Pu+vhKSYLhz3gC2K1H54f/v/"
    "THuaCEc8Yvh4EqtB5eG+0J0rDmlprncvgVEjsvczMep3U9fLf/KZe16x8/ffefH/65/26av"
    "qce3v+rdP7+R5La09plyvDC0/K4k8TTSmh0gdYC2soMyLbRwja1dYYmyN1vOjctIZxwMFOb"
    "EF568rwrv6AjPH2kPrsnrrudq0fq85UOiH5oq72SHykZujwXWjwV/wuJV3LXX8RKtBDDfMSV"
    "PoixU3quCk1FF+f+uaIdfazeG79/31aE6bVxvqee65HyX51n2t8rP1aUjWpl9WGuIFdrbFV"
    "ZeKmtcl4fn6XIL5rgSLqrHy77AjVtPwLx2c2fBl8opduurtk91bCDZT6MKX78jKWoPPdUnUI"
    "wucMPRIA3PfiXrerXefQHi/aLgrdr8ouCny+5F+E/wxCvo583N727pfpIJaSslqIEgss35Njf"
    "3lWup76O4bk6Zelc8zPUqs2DrcSRFsJUJtZlNczdcSFXSh9Z7E51u5lLbz69+RU="
)


def _load_diagnostic():
    assert SCRIPT.is_file(), (
        "missing tracked diagnostic: scripts/diagnose_huiji_corpus_fidelity.py"
    )
    spec = importlib.util.spec_from_file_location(
        "diagnose_huiji_corpus_fidelity_under_test", SCRIPT
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _canonical_json_bytes(
    value: object, *, trailing_newline: bool = True
) -> bytes:
    rendered = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    if trailing_newline:
        rendered += "\n"
    return rendered.encode("utf-8")


def _canonical_bytes(value: object) -> bytes:
    return _canonical_json_bytes(value, trailing_newline=True)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _identity(path: Path, raw: bytes, row_count: int | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "path": path.as_posix(),
        "sha256": _sha256(raw),
        "size_bytes": len(raw),
    }
    if row_count is not None:
        result["row_count"] = row_count
    return result


def _write_json(path: Path, value: object) -> dict[str, object]:
    raw = _canonical_bytes(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return _identity(path, raw)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> dict[str, object]:
    raw = b"".join(_canonical_bytes(row) for row in rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return _identity(path, raw, len(rows))


def _write_bytes(path: Path, raw: bytes) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return _identity(path, raw)


def _raw_identity(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return _identity(path, raw)


def _hashed(value: str) -> str:
    return _sha256(value.encode("utf-8"))


def _source_binding_token_id(value: object) -> str:
    return "source-binding:sha256:" + _sha256(
        _canonical_json_bytes(value, trailing_newline=False)
    )


def _approved_receipt_bytes(encoded: str) -> bytes:
    return zlib.decompress(base64.b64decode(encoded), -zlib.MAX_WBITS)


def _active_parent() -> dict[str, object]:
    return {
        "record_id": "story:9/profile",
        "entity_type": "story",
        "category": "story",
        "section_kind": "profile",
        "source_refs": [
            {
                "source_title": "Data:Story/9.json",
                "content_sha256": "a" * 64,
                "kind": "legacy-data-page",
            }
        ],
    }


def _active_child() -> dict[str, object]:
    return {
        "record_id": "story:9/profile:0000",
        "parent_id": "story:9/profile",
        "entity_type": "story",
        "category": "story",
        "section_kind": "profile",
        "source_refs": [
            {
                "source_title": "Data:Story/9.json",
                "content_sha256": "a" * 64,
                "kind": "legacy-data-page",
            }
        ],
    }


def _active_non_story_child() -> dict[str, object]:
    return {
        # Deliberately misleading prefix: the typed row, not this identifier,
        # is the authoritative Story/non-Story partition evidence.
        "record_id": "story:mismatched-prefix/profile:0000",
        "parent_id": "character:9/profile",
        "entity_type": "character",
        "category": "character",
        "section_kind": "profile",
        "source_refs": [
            {
                "source_title": "Data:Character/9.json",
                "content_sha256": "b" * 64,
                "kind": "legacy-data-page",
            }
        ],
    }


def _candidate_parent() -> dict[str, object]:
    return {
        "record_id": "story:9/story",
        "entity_id": "9",
        "entity_type": "story",
        "category": "story",
        "section_kind": "story",
        "source_refs": [
            {
                "source_title": "Data:Story/9.json",
                "content_sha256": "a" * 64,
                "kind": "data-page",
            }
        ],
    }


def _candidate_child(index: int) -> dict[str, object]:
    return {
        "record_id": f"story:9/story:step-{index:04d}",
        "parent_id": "story:9/story",
        "entity_id": "9",
        "entity_type": "story",
        "category": "story",
        "section_kind": "story",
        "source_token": f"$.steps[{index}]",
        "source_refs": [
            {
                "source_title": "Data:Story/9.json",
                "content_sha256": "a" * 64,
                "json_path": f"$.steps[{index}]",
                "kind": "data-page",
            }
        ],
    }


def _candidate_non_story_child() -> dict[str, object]:
    return {
        "record_id": "character:9/profile-v2:0000",
        "parent_id": "character:9/profile-v2",
        "entity_id": "9",
        "entity_type": "character",
        "category": "character",
        "section_kind": "profile-v2",
        "source_token": "$.profile",
        "source_refs": [
            {
                "source_title": "Data:Character/9.json",
                "content_sha256": "b" * 64,
                "json_path": "$.profile",
                "kind": "data-page",
            }
        ],
    }


def _story_ledger_row() -> dict[str, object]:
    return {
        "schema_version": "huiji.fidelity-ledger/v1",
        "ledger_id": "fidelity:sha256:" + "c" * 64,
        "record_kind": "child",
        "active_identity": "story:9/profile:0000",
        "candidate_identities": [
            "story:9/story:step-0000",
            "story:9/story:step-0001",
        ],
        "classification": "blocked_ambiguous",
        "reason_code": "candidate_identity_ambiguous",
        "active_sha256": _hashed("story-active-child"),
        "candidate_sha256": _hashed("story-candidate-children"),
        "source_evidence": [
            {
                "source_title": "Data:Story/9.json",
                "source_content_sha256": "a" * 64,
                "json_path": "$.steps",
            }
        ],
        "details": {"legacy_section": "profile", "candidate_section": "story"},
    }


def _non_story_ledger_row() -> dict[str, object]:
    return {
        "schema_version": "huiji.fidelity-ledger/v1",
        "ledger_id": "fidelity:sha256:" + "d" * 64,
        "record_kind": "child",
        # Deliberately misleading prefix: Story classification must come from
        # the accepted source-backed C8b audit, never this string prefix.
        "active_identity": "story:mismatched-prefix/profile:0000",
        "candidate_identities": ["character:9/profile-v2:0000"],
        "classification": "blocked_ambiguous",
        "reason_code": "candidate_identity_ambiguous",
        "active_sha256": _hashed("character-active-child"),
        "candidate_sha256": _hashed("character-candidate-child"),
        "source_evidence": [
            {
                "source_title": "Data:Character/9.json",
                "source_content_sha256": "b" * 64,
                "json_path": "$.profile",
            }
        ],
        "details": {"legacy_section": "profile", "candidate_section": "profile-v2"},
    }


def _c8c_taxonomy(
    active_media_rows: list[dict[str, object]],
) -> dict[str, object]:
    categories = (
        "ambiguous_binding",
        "ambiguous_binding",
        "conflicting_binding",
        "missing_local_bytes",
        "missing_local_bytes",
        "missing_local_bytes",
    )
    rows = []
    for index, (active_media_row, category) in enumerate(
        zip(active_media_rows, categories, strict=True)
    ):
        candidate_binding_ids = [
            (
                active_media_rows[0]["binding_id"]
                if category == "ambiguous_binding"
                else active_media_row["binding_id"]
            )
        ]
        raw_source_binding_token = (
            active_media_rows[0]["source_binding_token"]
            if category == "ambiguous_binding"
            else active_media_row["source_binding_token"]
        )
        rows.append(
            {
                "occurrence_id": "legacy-occurrence:sha256:"
                + f"{index + 1:x}" * 64,
                "legacy_row_sha256": _sha256(
                    _canonical_json_bytes(
                        active_media_row, trailing_newline=False
                    )
                ),
                "legacy_media_id": active_media_row["media_id"],
                "legacy_sha1": active_media_row["sha1"],
                "legacy_parent_id": active_media_row["parent_id"],
                "legacy_child_id": active_media_row["child_id"],
                "legacy_resource_identity_id": (
                    "legacy-resource:sha256:" + f"{index + 7:x}" * 64
                ),
                "category": category,
                "reason_code": f"verified_binding_{category}",
                "candidate_shape": "unique",
                "exact_candidate_count": 1,
                "candidate_binding_ids": candidate_binding_ids,
                "potential_candidate_ids": candidate_binding_ids,
                "candidate_source_binding_token_ids": [
                    _source_binding_token_id(raw_source_binding_token)
                ],
                "source_relation_shape": "unique",
                "successor_parent_count": 1,
                "successor_parent_ids": [
                    (
                        "character:conflict/profile"
                        if category == "conflicting_binding"
                        else "story:9/story"
                    )
                ],
                "successor_child_count": 1,
                "successor_child_ids": [
                    (
                        "character:conflict/profile:0000"
                        if category == "conflicting_binding"
                        else "story:9/story:step-0000"
                    )
                ],
                "owner_transition": True,
                "parent_transition": True,
                "child_transition": True,
                "current_closure_status": (
                    "conflicting"
                    if category == "conflicting_binding"
                    else "closed"
                ),
                "resource_metadata_present": True,
                "resource_metadata_conflicting": (
                    category == "conflicting_binding"
                ),
                "potential_candidate_collision": (
                    category == "ambiguous_binding"
                ),
                "local_byte_state": "absent",
                "local_size_verified": False,
                "local_sha1_verified": False,
                "local_sha256_verified": False,
                "protected_candidate_resource_evidence": False,
                "explicit_source_removal_evidence": False,
            }
        )
    return {
        "schema_version": "huiji.c8c-legacy-media-taxonomy/v1",
        "run_id": "task8-c-20260730T145113Z",
        "active_occurrence_count": len(active_media_rows),
        "category_counts": MEDIA_COUNTS,
        "bounded_samples": {},
        "coverage_checks": {
            "all_categories_known": True,
            "category_sum_equals_active_occurrence_count": True,
            "each_active_occurrence_exactly_once": True,
            "incomplete_evidence_explicit_count": len(active_media_rows),
            "potential_candidate_collision_count": 1,
            "proven_candidate_consumption_collision_count": 0,
        },
        "duplicate_consumption_checks": {
            "bounded_collision_samples": [
                {
                    "candidate_binding_id": active_media_rows[0]["binding_id"],
                    "occurrence_ids": [
                        "legacy-occurrence:sha256:" + "1" * 64,
                        "legacy-occurrence:sha256:" + "2" * 64,
                    ],
                }
            ],
            "duplicate_active_occurrence_id_count": 0,
            "potential_candidate_collision_count": 1,
            "proven_candidate_consumption_collision_count": 0,
        },
        "population_cross_check": {
            "accepted_baseline": len(active_media_rows),
            "accepted_fidelity_active_occurrences": len(active_media_rows),
            "accepted_fidelity_unexplained_binding_loss": len(active_media_rows),
            "legacy_jsonl": len(active_media_rows),
            "pinned_expected_result": len(active_media_rows),
        },
        "rows": rows,
    }


def _run_config(
    tmp_path: Path,
    *,
    accepted_taxonomy_manifest_row_count: int | None = None,
    protected_identity_manifest_row_count: int = 32,
    descendant_reviewed_file: str | None = None,
    protected_inside_repository: bool = False,
) -> tuple[Path, str, Path, dict[str, object]]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    repository = tmp_path / "repository"
    protected_state_root = (
        repository / "eval/story_segment/dependencies/protected-state"
        if protected_inside_repository
        else tmp_path / "protected-state"
    )
    evidence = repository / "frozen"
    output_root = tmp_path / RUN_ID
    repository.mkdir()
    protected_state_root.mkdir(parents=True)

    active_parent = _active_parent()
    active_child = _active_child()
    candidate_parent = _candidate_parent()
    candidate_children = [
        _candidate_child(0),
        _candidate_child(1),
        _candidate_non_story_child(),
    ]
    active_media_rows = [
        {
            "binding_id": "binding:sha256:" + f"{index + 1:x}" * 64,
            "media_id": "media:sha1:" + f"{index + 1:x}" * 40,
            "sha1": f"{index + 1:x}" * 40,
            "parent_id": "story:9/profile",
            "child_id": "story:9/profile:0000",
            "source_binding_token": f"wiki:legacy-media:{index}",
        }
        for index in range(6)
    ]
    # Repeated SHA1 values are valid legacy/resource facts when the concrete
    # filename/size identity distinguishes the resource rows.
    active_media_rows[1]["sha1"] = active_media_rows[0]["sha1"]
    active_media_rows[1]["media_id"] = active_media_rows[0]["media_id"]
    candidate_media_rows = []
    for index, active_media_row in enumerate(active_media_rows):
        filename = f"safe-{index}.png"
        title = f"Natural context for safe media {index}"
        content_sha256 = f"{index + 1:x}" * 64
        candidate_media_rows.append(
            {
                "binding_id": active_media_row["binding_id"],
                "resource_id": "resource:sha256:" + f"{index + 1:x}" * 64,
                "source_sha1": active_media_row["sha1"],
                "content_sha256": content_sha256,
                "content_hash": f"sha256:{content_sha256}",
                "size": 123 + index,
                "filename": filename,
                "title": title,
                "source_binding_token": active_media_row["source_binding_token"],
                "parent_id": (
                    "character:conflict/profile"
                    if index == 2
                    else "story:9/story"
                ),
                "child_id": (
                    "character:conflict/profile:0000"
                    if index == 2
                    else "story:9/story:step-0000"
                ),
            }
        )
    resource_rows = [
        {
            "descriptionurl": f"https://example.invalid/wiki/File:Safe-{index}.png",
            "download_status": "not_downloaded",
            "height": 1,
            "local_relpath": f"media/safe-{index}.png",
            "mime": "image/png",
            "name": f"safe-{index}.png",
            "sha1": active_media_row["sha1"],
            "seen_at": "2026-07-30T00:00:00Z",
            "site": "huijiwiki.com",
            "size": 123 + index,
            "source": "api:imageinfo",
            "timestamp": "2026-07-30T00:00:00Z",
            "title": f"File:Safe-{index}.png",
            "url": f"https://example.invalid/media/safe-{index}.png",
            "width": 1,
        }
        for index, active_media_row in enumerate(active_media_rows)
    ]
    resource_rows.append(
        {
            "descriptionurl": "https://example.invalid/wiki/File:Unrelated.bin",
            "download_status": "not_downloaded",
            "height": 0,
            "local_relpath": "media/unrelated.bin",
            "mime": "application/octet-stream",
            "name": "unrelated.bin",
            "sha1": "f" * 40,
            "seen_at": "2026-07-30T00:00:00Z",
            "site": "huijiwiki.com",
            "size": 987,
            "source": "api:imageinfo",
            "timestamp": "2026-07-30T00:00:00Z",
            "title": "File:Unrelated.bin",
            "url": "https://example.invalid/media/unrelated.bin",
            "width": 0,
        }
    )
    local_media_raw = b"local media bytes must never be read\n"
    resource_rows[0] = {
        **resource_rows[0],
        "name": "arbitrary-resource.dat",
        "title": "File:Arbitrary resource.dat",
        "local_relpath": "media/arbitrary-resource.dat",
    }
    for candidate_media_row in candidate_media_rows:
        if candidate_media_row["source_sha1"] == resource_rows[0]["sha1"]:
            if candidate_media_row["size"] == resource_rows[0]["size"]:
                candidate_media_row["filename"] = resource_rows[0]["name"]
    local_media_path = evidence / "crawler" / str(resource_rows[0]["local_relpath"])
    local_media_path.parent.mkdir(parents=True)
    local_media_path.write_bytes(local_media_raw)

    inputs: dict[str, dict[str, object]] = {
        "active_parents": _write_jsonl(evidence / "active-parents.jsonl", [active_parent]),
        "active_children": _write_jsonl(
            evidence / "active-children.jsonl",
            [active_child, _active_non_story_child()],
        ),
        "active_excluded": _write_jsonl(evidence / "active-excluded.jsonl", []),
        "active_child_bm25": _write_json(
            evidence / "active-child-bm25.json", {"records": []}
        ),
        "active_media_bm25": _write_json(
            evidence / "active-media-bm25.json", {"records": []}
        ),
        "candidate_parents": _write_jsonl(
            evidence / "candidate-parents.jsonl", [candidate_parent]
        ),
        "candidate_children": _write_jsonl(
            evidence / "candidate-children.jsonl", candidate_children
        ),
        "active_media": _write_jsonl(
            evidence / "active-media.jsonl", active_media_rows
        ),
        "candidate_media_v3": _write_jsonl(
            evidence / "candidate-media.v3.jsonl", candidate_media_rows
        ),
        "resource_metadata": _write_jsonl(
            evidence / "crawler" / "resources_manifest.jsonl",
            resource_rows,
        ),
    }
    inputs["c8b_story_ledger"] = _write_jsonl(
        evidence / "fidelity-ledger.c8b.jsonl",
        [_story_ledger_row(), _non_story_ledger_row()],
    )
    taxonomy = _c8c_taxonomy(active_media_rows)
    inputs["c8b_taxonomy"] = _write_json(
        evidence / "taxonomy.c8b3.v1.json",
        {
            "schema_version": "huiji.task8-c8b-story-legacy-taxonomy/v1",
            "decision_matrix": {},
            "dynamic_counts": {},
            "inputs": {},
            "mode": "read_only",
            "one_to_one_migration_pair_audit": {},
            "policy_selection": {},
            "run": {"run_id": "task8-c-20260729T161119Z"},
            "stage_metrics": {},
            "status": "completed_pending_review",
            "story_record_link_evidence": {
                "parent": {
                    "candidate_count": 1,
                    "missing_record_link_count": 1,
                    "new_source_record_link_count": 1,
                    "source_ref_complete_count": 1,
                },
                "child": {
                    "candidate_count": 2,
                    "missing_record_link_count": 2,
                    "new_source_record_link_count": 2,
                    "source_ref_complete_count": 2,
                    "stable_source_token_kind_counts": {"json_path": 2},
                },
                "missing_record_link_causes": [
                    {
                        "observed_behavior": "record_link_not_emitted",
                        "record_kind": "parent",
                        "source_function": "project_story_parent",
                        "source_stage": "data_projection",
                    },
                    {
                        "observed_behavior": "record_link_not_emitted",
                        "record_kind": "child",
                        "source_function": "project_story_steps",
                        "source_stage": "data_projection",
                    },
                    {
                        "observed_behavior": "record_link_not_emitted",
                        "record_kind": "child",
                        "source_function": "compose_corpus_projection",
                        "source_stage": "composed_projection",
                    },
                ],
            },
            "safety": {"protected_identity_count": 32, "protected_drift_count": 0},
            "samples": {},
            "taxonomy": {},
        },
    )
    c8b_taxonomy_identity = inputs["c8b_taxonomy"]
    c8b_manifest_witnesses = (
        (
            "taxonomy.py",
            _write_bytes(
                evidence / "taxonomy.py",
                b"# pinned C8b taxonomy diagnostic fixture\n",
            ),
        ),
        (
            "protected_pre.c8b3.v1.json",
            _write_json(
                evidence / "protected_pre.c8b3.v1.json",
                {"fixture": "pinned C8b protected state"},
            ),
        ),
        ("taxonomy.c8b3.v1.json", c8b_taxonomy_identity),
        (
            "protected_post.c8b3.v1.json",
            _write_json(
                evidence / "protected_post.c8b3.v1.json",
                {"fixture": "pinned C8b protected state"},
            ),
        ),
        (
            "protected_compare.c8b3.v1.json",
            _write_json(
                evidence / "protected_compare.c8b3.v1.json",
                {"protected_drift_count": 0, "protected_identity_count": 32},
            ),
        ),
    )
    c8b_manifest_files = [
        {
            "basename": basename,
            "label": basename,
            "mtime_ns": Path(identity["path"]).stat().st_mtime_ns,
            "sha256": identity["sha256"],
            "size": identity["size_bytes"],
        }
        for basename, identity in c8b_manifest_witnesses
    ]
    _write_json(
        evidence / "manifest.c8b3.v1.json",
        {
            "checkpoint_commit": C8A_COMMIT,
            "files": c8b_manifest_files,
            "protected_drift_count": 0,
            "protected_identity_count": 32,
            "run_id": "task8-c-20260729T161119Z",
            "schema_version": "huiji.task8-c8b-evidence-manifest/v1",
            "status": "completed_pending_review",
        },
    )
    inputs["c8c_taxonomy"] = _write_json(
        evidence / "taxonomy.c8c-legacy-media.v1.json", taxonomy
    )
    protected_rows = []
    for index in range(32):
        protected_path = protected_state_root / f"target-{index:02d}.txt"
        protected_raw = f"protected target {index:02d}\n".encode()
        protected_path.parent.mkdir(parents=True, exist_ok=True)
        protected_path.write_bytes(protected_raw)
        stat = protected_path.stat()
        protected_rows.append(
            {
                "label": f"protected_target_{index:02d}",
                "path": protected_path.as_posix(),
                "sha256": _sha256(protected_raw),
                "size": len(protected_raw),
                "mtime_ns": stat.st_mtime_ns,
            }
        )
    inputs["protected_identity_manifest"] = _write_json(
        evidence / "protected_pre.v1.json",
        {
            "schema_version": "huiji.task8-protected-state/v1",
            "records": protected_rows,
        },
    )

    for filename in CRAWLER_SOURCES[:3]:
        label = f"crawler_{Path(filename).stem}"
        inputs[label] = _write_jsonl(
            evidence / "crawler" / filename,
            [{"title": filename, "content_sha256": _hashed(filename)}],
        )
    # These two C8d labels are one pinned C8c/raw-crawler fact, not two
    # independently editable resource manifests.
    inputs["crawler_resources_manifest"] = inputs["resource_metadata"]

    c8b_receipt = evidence / "d-acceptance-c8b.json"
    c8b_receipt.write_bytes(_approved_receipt_bytes(C8B_RECEIPT_DEFLATE_BASE64))
    c8c_receipt = evidence / "d-accept-c8c-final.json"
    c8c_receipt.write_bytes(_approved_receipt_bytes(C8C_RECEIPT_DEFLATE_BASE64))
    assert _sha256(c8b_receipt.read_bytes()) == C8B_RECEIPT_SHA256
    assert _sha256(c8c_receipt.read_bytes()) == C8C_RECEIPT_SHA256
    accepted_checkpoints = {
        "task7_c8a_commit": C8A_COMMIT,
        "c8b_commit": C8B_COMMIT,
        "c8b_d_acceptance": {
            "path": c8b_receipt.as_posix(),
            "sha256": C8B_RECEIPT_SHA256,
            "size_bytes": c8b_receipt.stat().st_size,
        },
        "c8c_commit": C8C_COMMIT,
        "c8c_d_acceptance": {
            "path": c8c_receipt.as_posix(),
            "sha256": C8C_RECEIPT_SHA256,
            "size_bytes": c8c_receipt.stat().st_size,
        },
    }
    parity_status = "c8c_real_snapshot_product_parity_pending_d_review"
    parity_forbidden_counters = {
        "activation_calls": 0,
        "active_pointer_changes": 0,
        "media_download_calls": 0,
        "milvus_calls": 0,
        "minio_calls": 0,
        "mysql_calls": 0,
        "network_calls": 0,
        "production_writes": 0,
        "subprocess_calls": 0,
        "vector_rebuild_calls": 0,
        "writes_outside_run_directory": 0,
    }
    accepted_taxonomy_rows_sha256 = _sha256(
        _canonical_bytes(taxonomy["rows"])
    )
    product_ledger_sha256 = _sha256(
        _canonical_json_bytes(
            {
                "evidence_class": "product-occurrence-ledger",
                "accepted_taxonomy_rows_sha256": (
                    accepted_taxonomy_rows_sha256
                ),
                "run_id": "task8-c-product-parity-20260730T190741Z",
            },
            trailing_newline=False,
        )
    )
    assert product_ledger_sha256 != accepted_taxonomy_rows_sha256
    product_summary = {
        "schema_version": "huiji.c8c-product-parity-summary/v1",
        "run_id": "task8-c-product-parity-20260730T190741Z",
        "head": C8B_COMMIT,
        "tree": "d612af9038026eb7b01ebccb5b5f3e22b04ddffd",
        "status": parity_status,
        "accepted_taxonomy": {
            "active_occurrence_count": 6,
            "category_counts": taxonomy["category_counts"],
            "unexplained_binding_loss": 6,
        },
        "active_occurrence_count": 6,
        "category_counts": taxonomy["category_counts"],
        "elapsed_seconds": 0.0,
        "fidelity": {
            "blocker_prefix_counts": {
                "legacy_media_ambiguous_binding": 1,
                "legacy_media_conflicting_binding": 1,
                "legacy_media_missing_local_bytes": 1,
                "unexplained_binding_loss": 1,
            },
            "legacy_media_blocker_counts": {
                "legacy_media_ambiguous_binding:2": 1,
                "legacy_media_conflicting_binding:1": 1,
                "legacy_media_missing_local_bytes:3": 1,
                "legacy_media_missing_resource_metadata:0": 0,
                "unexplained_binding_loss:6": 1,
            },
            "non_media_blocker_prefix_counts": {},
            "returned": True,
            "unexplained_binding_loss": 6,
        },
        "forbidden_action_counters": parity_forbidden_counters,
        "observed_audit_events": {
            "loopback_capability_probe_binds": 0,
            "socket_capability_probe_constructors": 0,
        },
        "parity": {
            "active_occurrence_count_equal": True,
            "all_seven_category_counts_equal": True,
            "unexplained_binding_loss_equal": True,
        },
        "peak_rss_bytes": 0,
        "product_interface": (
            "src.huiji_rag.build.media_v3.reconcile_active_media_occurrences"
        ),
        "product_occurrence_ledger_sha256": product_ledger_sha256,
        "protected_state": {
            "identity_count": 32,
            "drift_count": 0,
            "state_sha256_pre": _hashed("protected-state"),
            "state_sha256_post": _hashed("protected-state"),
        },
        "stage_elapsed_seconds": {
            "compose_projection": 0.0,
            "data_projection": 0.0,
            "load_accepted_taxonomy": 0.0,
            "load_active_baseline": 0.0,
            "load_active_media": 0.0,
            "load_candidate_media": 0.0,
            "load_fidelity_active_rows": 0.0,
            "page_projection": 0.0,
            "page_revision_join": 0.0,
            "preflight_input_hashing": 0.0,
            "resource_manifest_projection": 0.0,
            "tracked_fidelity_ledger": 0.0,
            "tracked_media_reconciliation": 0.0,
        },
        "unexplained_binding_loss": 6,
    }
    product_summary_ref = _write_json(
        evidence / "summary.product-parity.v1.json", product_summary
    )
    product_diagnostic_path = evidence / "diagnostic.product-parity.py"
    product_diagnostic_path.write_bytes(b"# frozen product parity diagnostic\n")
    product_diagnostic_sha256 = _sha256(product_diagnostic_path.read_bytes())
    accepted_baseline_witness = _write_json(
        repository
        / "eval/huiji_corpus_fidelity/20260720T073917Z/corpus-preservation-baseline.v2.json",
        {
            "schema_version": "huiji.corpus-preservation-baseline/v2",
            "status": "pass",
            "active_artifacts": {
                "files": {
                    filename: {
                        "path": Path(inputs[label]["path"])
                        .relative_to(repository)
                        .as_posix(),
                        "sha256": inputs[label]["sha256"],
                        "size": inputs[label]["size_bytes"],
                    }
                    for filename, label in (
                        ("parent_blocks.jsonl", "active_parents"),
                        ("child_blocks.jsonl", "active_children"),
                        ("excluded_entities.jsonl", "active_excluded"),
                        ("media_assets.jsonl", "active_media"),
                        ("child_text_bm25.json", "active_child_bm25"),
                        ("media_asset_bm25.json", "active_media_bm25"),
                    )
                }
            },
        },
    )
    c8c_review_witnesses = (
        _write_json(
            repository
            / ".codex-supervisor/workers/C/d-review-c8c-real-interface-accepted.json",
            {
                "schema_version": "fixture.c8c-real-interface-review/v1",
                "status": "accepted",
            },
        ),
        _write_json(
            repository
            / ".codex-supervisor/workers/C/d-review-c8c-final-43-green.json",
            {
                "schema_version": "fixture.c8c-green-review/v1",
                "status": "accepted",
            },
        ),
    )
    reviewed_file_paths = (
        "src/huiji_rag/build/media_v3.py",
        "src/huiji_rag/build/fidelity.py",
        "src/huiji_rag/build/orchestrator.py",
        "tests/test_huiji_media_v3_builder.py",
        "tests/test_huiji_corpus_fidelity.py",
        "docs/superpowers/specs/2026-07-29-rag-thread-c-legacy-media-decision.md",
    )
    source_repository = SCRIPT.parents[1]

    def git_blob(commit: str, relative_path: str) -> bytes:
        return subprocess.run(
            ("git", "show", f"{commit}:{relative_path}"),
            cwd=source_repository,
            check=True,
            capture_output=True,
            shell=False,
        ).stdout

    reviewed_file_witnesses = tuple(
        _write_bytes(
            repository / relative_path,
            git_blob(C8C_COMMIT, relative_path),
        )
        for relative_path in reviewed_file_paths
    )
    # Preserve the accepted C8c product-manifest sequence as a list and bind
    # every witness explicitly to the corresponding C8d fixture identity.
    manifest_witnesses = (
        ("d_acceptance_receipt", c8c_review_witnesses[0]),
        ("d_green_review_receipt", c8c_review_witnesses[1]),
        ("legacy_active_media", inputs["active_media"]),
        ("accepted_taxonomy", inputs["c8c_taxonomy"]),
        ("candidate_media_v3", inputs["candidate_media_v3"]),
        ("accepted_baseline", accepted_baseline_witness),
        ("protected_identity_manifest", inputs["protected_identity_manifest"]),
        ("pages", inputs["crawler_pages"]),
        ("wikitext", inputs["crawler_wikitext"]),
        ("data_pages", inputs["crawler_data_pages"]),
        ("resources_manifest", inputs["crawler_resources_manifest"]),
        *(("reviewed_file", identity) for identity in reviewed_file_witnesses),
    )
    product_manifest_inputs = [
        {
            "identity": Path(identity["path"]).relative_to(repository).as_posix(),
            "label": label,
            "row_count": (
                len(taxonomy["rows"])
                if label == "accepted_taxonomy"
                and accepted_taxonomy_manifest_row_count is None
                else accepted_taxonomy_manifest_row_count
                if label == "accepted_taxonomy"
                else protected_identity_manifest_row_count
                if label == "protected_identity_manifest"
                else identity.get("row_count")
            ),
            "sha256": identity["sha256"],
            "size": identity["size_bytes"],
        }
        for label, identity in manifest_witnesses
    ]
    product_manifest = {
        "schema_version": "huiji.c8c-product-parity-manifest/v1",
        "run_id": product_summary["run_id"],
        "head": product_summary["head"],
        "tree": product_summary["tree"],
        "status": parity_status,
        "diagnostic_script_sha256": product_diagnostic_sha256,
        "forbidden_action_counters": parity_forbidden_counters,
        "inputs": product_manifest_inputs,
        "interpreter": {
            "identity": "conda:1999wiki/python.exe",
            "version": "3.11.15",
        },
        "outputs": {
            "summary.product-parity.v1.json": product_summary_ref["sha256"]
        },
        "protected_identity_count": 32,
        "protected_drift_count": 0,
    }
    product_manifest_ref = _write_json(
        evidence / "manifest.product-parity.v1.json", product_manifest
    )
    product_receipt = {
        "schema_version": "huiji.c8c-product-parity-receipt/v1",
        "run_id": product_summary["run_id"],
        "head": product_summary["head"],
        "tree": product_summary["tree"],
        "status": parity_status,
        "active_occurrence_count": 6,
        "category_counts": taxonomy["category_counts"],
        "commit_created": False,
        "forbidden_action_counters": parity_forbidden_counters,
        "output_sha256": {
            "diagnostic.product-parity.py": product_manifest[
                "diagnostic_script_sha256"
            ],
            "manifest.product-parity.v1.json": product_manifest_ref["sha256"],
            "summary.product-parity.v1.json": product_summary_ref["sha256"],
        },
        "protected_identity_count": 32,
        "protected_drift_count": 0,
        "staged_path_count": 0,
        "tracked_files_modified": False,
        "unexplained_binding_loss": 6,
    }
    product_receipt_ref = _write_json(
        evidence / "receipt.product-parity.v1.json", product_receipt
    )
    inputs.update(
        {
            "c8c_product_manifest": product_manifest_ref,
            "c8c_product_summary": product_summary_ref,
            "c8c_product_receipt": product_receipt_ref,
        }
    )

    diagnostic_path = repository / SCRIPT_RELATIVE_PATH
    diagnostic_path.parent.mkdir(parents=True)
    diagnostic_path.write_bytes(SCRIPT_BYTES)
    subprocess.run(
        ("git", "init", "--quiet"),
        cwd=repository,
        check=True,
        capture_output=True,
        shell=False,
    )
    source_git_objects = subprocess.run(
        ("git", "rev-parse", "--git-path", "objects"),
        cwd=source_repository,
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    ).stdout.strip()
    alternates = repository / ".git/objects/info/alternates"
    alternates.parent.mkdir(parents=True, exist_ok=True)
    alternates.write_bytes(
        Path(source_git_objects).resolve().as_posix().encode("utf-8") + b"\n"
    )
    expected_head = HEAD
    expected_tree = TREE
    if descendant_reviewed_file is not None:
        if descendant_reviewed_file not in reviewed_file_paths:
            raise AssertionError("descendant fixture path is not reviewed")
        historical = git_blob(C8C_COMMIT, descendant_reviewed_file)
        descendant = git_blob(DESCENDANT_HEAD, descendant_reviewed_file)
        assert descendant != historical
        (repository / descendant_reviewed_file).write_bytes(descendant)
        expected_head = DESCENDANT_HEAD
        expected_tree = DESCENDANT_TREE
    config: dict[str, object] = {
        "schema_version": "huiji.c8d-fidelity-run-config/v1",
        "run_id": RUN_ID,
        "repository_root": repository.as_posix(),
        "protected_state_root": protected_state_root.as_posix(),
        "output_root": output_root.as_posix(),
        "expected_git_head": expected_head,
        "expected_git_tree": expected_tree,
        "diagnostic": {
            "path": SCRIPT_RELATIVE_PATH,
            "sha256": SCRIPT_SHA256,
        },
        "accepted_checkpoints": accepted_checkpoints,
        "expected_output_files": list(OUTPUT_NAMES),
        "sample_limit_per_blocker_prefix": 5,
        "expected_protected_identity_count": 32,
        "expected_protected_drift_count": 0,
        "expected_legacy_media_category_counts": MEDIA_COUNTS,
        "inputs": inputs,
        "c8c_evidence_chain": {
            "manifest_sha256": product_manifest_ref["sha256"],
            "summary_sha256": product_summary_ref["sha256"],
            "receipt_sha256": product_receipt_ref["sha256"],
            "occurrence_ledger_sha256": product_summary[
                "product_occurrence_ledger_sha256"
            ],
        },
    }
    config_path = tmp_path / "run-config.c8d.json"
    config_raw = _canonical_bytes(config)
    config_path.write_bytes(config_raw)
    return config_path, _sha256(config_raw), output_root, config


def _commit_tree(repository: Path, tree: str, parent: str, message: str) -> str:
    environment = {
        **os.environ,
        "GIT_AUTHOR_NAME": "C9c fixture",
        "GIT_AUTHOR_EMAIL": "c9c@example.invalid",
        "GIT_AUTHOR_DATE": "2026-08-02T00:00:00Z",
        "GIT_COMMITTER_NAME": "C9c fixture",
        "GIT_COMMITTER_EMAIL": "c9c@example.invalid",
        "GIT_COMMITTER_DATE": "2026-08-02T00:00:00Z",
    }
    return subprocess.run(
        ("git", "commit-tree", tree, "-p", parent, "-m", message),
        cwd=repository,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    ).stdout.strip()


def _c9_intake(
    tmp_path: Path,
) -> tuple[Path, Path, str, Path, dict[str, object], dict[str, object]]:
    _config_path, _digest, _old_output, config = _run_config(
        tmp_path, protected_inside_repository=True
    )
    project_root = Path(config["repository_root"])
    c8d_commit = str(config["expected_git_head"])
    checkpoint_tree = str(config["expected_git_tree"])
    c9_commit = _commit_tree(
        project_root, checkpoint_tree, c8d_commit, "C9 zero-diff checkpoint"
    )
    post_merge_commit = _commit_tree(
        project_root, checkpoint_tree, c9_commit, "post-merge descendant"
    )
    config["expected_git_head"] = post_merge_commit
    config["expected_git_tree"] = checkpoint_tree
    subprocess.run(
        ("git", "update-ref", "refs/heads/main", post_merge_commit),
        cwd=project_root,
        check=True,
        capture_output=True,
        shell=False,
    )
    subprocess.run(
        ("git", "symbolic-ref", "HEAD", "refs/heads/main"),
        cwd=project_root,
        check=True,
        capture_output=True,
        shell=False,
    )
    dependency_root = project_root / "eval/story_segment/dependencies/intake-fixture"
    dependency_root.mkdir(parents=True)
    handoff_path = dependency_root / "audit-handoff.c9.v1.json"
    handoff = {
        "schema_version": "huiji.thread-c-c9-audit/v1",
        "run_id": "task9-c-intake-fixture",
        "status": "completed",
        "c9_complete": True,
        "merge_ready": True,
        "disposition": "completed_pending_review",
        "git_identity": {
            "head": c9_commit,
            "tree": checkpoint_tree,
            "parent": c8d_commit,
            "checkpoint_parent_tracked_diff_empty": True,
        },
        "commit_chain": {
            "head_inclusive": c9_commit,
        },
        "c9_test_evidence": {},
        "deterministic_closure": {"gate_closed": True},
        "c8d_real6_evidence": {},
        "remaining_blocker_classification": {
            "unresolved_deterministic_closure_blocker": False,
            "unresolved_candidate_cli_blocker": False,
        },
        "ownership_audit": {
            "tracked_worktree_clean": True,
            "index_clean": True,
            "unmerged_clean": True,
            "forbidden_ab_runtime_diff_empty": True,
            "external_operation_performed": False,
            "external_operation_counts": {
                "candidate_build": 0,
                "c8d": 0,
                "download": 0,
                "embedding_or_vector": 0,
                "milvus": 0,
                "minio": 0,
                "mysql": 0,
                "network": 0,
                "production_write": 0,
                "activation_or_pointer_change": 0,
            },
            "newly_tracked_forbidden_artifacts": {
                "raw_snapshot": False,
                "ignored_run": False,
                "pytest_basetemp": False,
                "supervisor_state": False,
                "vector_artifact": False,
                "downloaded_media": False,
                "production_pointer": False,
                "credentials": False,
            },
        },
        "canonical_text_or_child_ids_changed": True,
        "vector_rebuild_disposition": {"decision_owner": "D"},
    }
    handoff_raw = _canonical_bytes(handoff)
    handoff_path.write_bytes(handoff_raw)

    def relative_identity(identity: dict[str, object]) -> dict[str, object]:
        result = {
            "relative_path": Path(identity["path"])
            .relative_to(project_root)
            .as_posix(),
            "sha256": identity["sha256"],
            "size_bytes": identity["size_bytes"],
        }
        if "row_count" in identity:
            result["row_count"] = identity["row_count"]
        return result

    accepted = config["accepted_checkpoints"]
    intake: dict[str, object] = {
        "schema_version": "rag.thread-c9-intake/v1",
        "release_checkpoints": {
            "task7_c8a_commit": accepted["task7_c8a_commit"],
            "c8b_commit": accepted["c8b_commit"],
            "c8c_commit": accepted["c8c_commit"],
            "c8d_commit": c8d_commit,
            "c9_commit": c9_commit,
            "c9_tree": checkpoint_tree,
        },
        "c9_handoff": {
            "relative_path": handoff_path.relative_to(project_root).as_posix(),
            "sha256": _sha256(handoff_raw),
            "size_bytes": len(handoff_raw),
            "schema_version": "huiji.thread-c-c9-audit/v1",
        },
        "c8d_entrypoint": {
            "relative_path": SCRIPT_RELATIVE_PATH,
            "sha256": config["diagnostic"]["sha256"],
            "size_bytes": (project_root / SCRIPT_RELATIVE_PATH).stat().st_size,
            "schema_version": "huiji.corpus-fidelity-diagnostic/v1",
        },
        "protected_state_root": Path(config["protected_state_root"])
        .relative_to(project_root)
        .as_posix(),
        "accepted_evidence": {
            "c8b_d_acceptance": relative_identity(accepted["c8b_d_acceptance"]),
            "c8c_d_acceptance": relative_identity(accepted["c8c_d_acceptance"]),
        },
        "expected_output_files": list(OUTPUT_NAMES),
        "sample_limit_per_blocker_prefix": config[
            "sample_limit_per_blocker_prefix"
        ],
        "expected_protected_identity_count": config[
            "expected_protected_identity_count"
        ],
        "expected_protected_drift_count": config["expected_protected_drift_count"],
        "expected_legacy_media_category_counts": config[
            "expected_legacy_media_category_counts"
        ],
        "inputs": {
            label: relative_identity(identity)
            for label, identity in config["inputs"].items()
        },
        "c8c_evidence_chain": copy.deepcopy(config["c8c_evidence_chain"]),
    }
    intake_path = dependency_root / "c9-intake-receipt.v1.json"
    intake_raw = _canonical_bytes(intake)
    intake_path.write_bytes(intake_raw)
    output_root = project_root / "eval/story_segment/dependencies/run-fixture/c8d"
    output_root.parent.mkdir(parents=True)
    return (
        project_root,
        intake_path,
        _sha256(intake_raw),
        output_root,
        intake,
        config,
    )


def _rewrite_handoff_and_intake(
    project_root: Path,
    intake_path: Path,
    intake: dict[str, object],
    mutate: Callable[[dict[str, object]], None],
) -> str:
    handoff_path = project_root / intake["c9_handoff"]["relative_path"]
    handoff = json.loads(handoff_path.read_bytes())
    mutate(handoff)
    handoff_raw = _canonical_bytes(handoff)
    handoff_path.write_bytes(handoff_raw)
    intake["c9_handoff"]["sha256"] = _sha256(handoff_raw)
    intake["c9_handoff"]["size_bytes"] = len(handoff_raw)
    intake_raw = _canonical_bytes(intake)
    intake_path.write_bytes(intake_raw)
    return _sha256(intake_raw)


def _test_evidence_fixture() -> SimpleNamespace:
    return SimpleNamespace(
        data_projection=SimpleNamespace(
            parents=(),
            children=(),
            exclusions=(),
            record_links=(),
            voice_sources=(),
            media_intents=(),
            identity_fallbacks=(),
        ),
        page_projection=SimpleNamespace(
            parents=(),
            children=(),
            pages=(),
            sections=(),
            diagnostics=(),
            exclusions=(),
            media_intents=(),
        ),
        topic_projection=SimpleNamespace(
            parents=(),
            children=(),
            diagnostics=(),
            catalog_fingerprint_sha256="0" * 64,
        ),
        active_parent_rows=(_active_parent(),),
        active_child_rows=(_active_child(), _active_non_story_child()),
        active_excluded_rows=(),
        active_child_bm25_records=(),
        active_media_bm25_records=(),
        candidate_parent_rows=(_candidate_parent(),),
        candidate_child_rows=(
            _candidate_child(0),
            _candidate_child(1),
            _candidate_non_story_child(),
        ),
        story_ledger_rows=(_story_ledger_row(), _non_story_ledger_row()),
        legacy_media=SimpleNamespace(
            occurrence_rows=tuple(
                SimpleNamespace(
                    occurrence_id="legacy-occurrence:sha256:"
                    + f"{index + 1:x}" * 64,
                    category=category,
                )
                for index, category in enumerate(
                    (
                        "ambiguous_binding",
                        "ambiguous_binding",
                        "conflicting_binding",
                        "missing_local_bytes",
                        "missing_local_bytes",
                        "missing_local_bytes",
                    )
                )
            ),
            category_counts=MEDIA_COUNTS,
            unexplained_binding_loss=6,
            active_occurrence_count=6,
        ),
    )


def _fidelity_result() -> SimpleNamespace:
    return SimpleNamespace(
        passed=False,
        blockers=(
            "blocked_ambiguous_child:1",
            "blocked_ambiguous_child:1",
            "blocked_ambiguous_parent:1",
            "legacy_media_ambiguous_binding:2",
            "legacy_media_conflicting_binding:1",
            "legacy_media_missing_local_bytes:3",
            "unexplained_binding_loss:6",
            "unexplained_child_missing:1",
            "unexplained_parent_child_loss:1",
            "unexplained_parent_missing:1",
        ),
        category_counts={"blocked_ambiguous": 2},
        unexplained_parent_child_loss=1,
        unexplained_binding_loss=6,
        ledger_rows=(_story_ledger_row(), _non_story_ledger_row()),
        build_diff={},
    )


def _invoke(module: Any, config_path: Path, digest: str, output_root: Path) -> Any:
    return module.run_diagnostic(
        config_path,
        expected_run_config_sha256=digest,
        output_root=output_root,
    )


def _assert_no_output(output_root: Path) -> None:
    assert not output_root.exists() or not tuple(output_root.iterdir())


def test_blocker_prefix_counts_distinguishes_aggregates_from_instance_identities(
) -> None:
    module = _load_diagnostic()
    blockers = (
        "blocked_ambiguous_child:story:1dfff1dd76af:0000:"
        "story_profile_requires_exact_source_migration_link",
        "blocked_ambiguous_child:story:290dcce93c25:0001:"
        "story_profile_requires_exact_source_migration_link",
        "active_media_bm25_sequence_mismatch:15756",
        "future_instance_blocker:story:88d21e466ae1:0002:reason:with:colons",
        "legacy_media_missing_local_bytes:2",
        "legacy_media_missing_resource_metadata:0",
        "legacy_media_ambiguous_binding:4",
        "legacy_media_conflicting_binding:5",
        "unexplained_binding_loss:6",
        "unexplained_parent_child_loss:7",
    )

    assert dict(module._blocker_prefix_counts(blockers)) == {
        "active_media_bm25_sequence_mismatch": 1,
        "blocked_ambiguous_child": 2,
        "future_instance_blocker": 1,
        "legacy_media_ambiguous_binding": 4,
        "legacy_media_conflicting_binding": 5,
        "legacy_media_missing_local_bytes": 2,
        "legacy_media_missing_resource_metadata": 0,
        "unexplained_binding_loss": 6,
        "unexplained_parent_child_loss": 7,
    }

    malformed = (
        "legacy_media_missing_local_bytes",
        "legacy_media_missing_local_bytes:",
        "legacy_media_missing_local_bytes:01",
        "legacy_media_missing_local_bytes:-1",
        "legacy_media_missing_local_bytes:1:extra",
        ":story:1dfff1dd76af:0000:reason",
        "invalid-prefix:story:1dfff1dd76af:0000:reason",
        "Invalid_prefix:story:1dfff1dd76af:0000:reason",
    )
    for blocker in malformed:
        with pytest.raises(ValueError):
            module._blocker_prefix_counts((blocker,))


def test_load_validated_evidence_matches_candidate_json_boundary_and_id_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.huiji_rag.build.projection import SemanticChild
    from src.huiji_rag.models import ChildBlock, ParentBlock

    module = _load_diagnostic()
    _config_path, _digest, _output_root, config = _run_config(tmp_path)

    parent_a = ParentBlock.from_json(
        {
            "parent_id": "character:1/alpha",
            "entity_id": "1",
            "entity_name": "Alpha",
            "entity_aliases": ["A"],
            "category": "character",
            "section_kind": "profile",
            "title": "Alpha",
            "summary_text": "Alpha summary",
            "source_refs": [{"kind": "data-page", "source_title": "Alpha"}],
            "child_ids": ["character:1/alpha:0000"],
            "content_hash": "a" * 64,
        }
    )
    parent_b = ParentBlock.from_json(
        {
            "parent_id": "character:2/beta",
            "entity_id": "2",
            "entity_name": "Beta",
            "entity_aliases": ["B"],
            "category": "character",
            "section_kind": "profile",
            "title": "Beta",
            "summary_text": "Beta summary",
            "source_refs": [{"kind": "data-page", "source_title": "Beta"}],
            "child_ids": ["character:2/beta:0000"],
            "content_hash": "b" * 64,
        }
    )

    def semantic_child(
        *, child_id: str, parent_id: str, entity_id: str, token: str
    ) -> SemanticChild:
        block = ChildBlock.from_json(
            {
                "child_id": child_id,
                "parent_id": parent_id,
                "entity_id": entity_id,
                "entity_name": entity_id,
                "category": "character",
                "section_kind": "profile",
                "title": entity_id,
                "text": f"{entity_id} text",
                "search_text": f"{entity_id} search",
                "chunk_index": 0,
                "media_ids": [f"media:{entity_id}"],
                "media_policy": "auto",
                "source_refs": [{"kind": "data-page", "source_title": entity_id}],
                "content_hash": entity_id * 64,
            }
        )
        return SemanticChild(
            block=block,
            stable_source_token=token,
            source_token_kind="json_path",
            owner_entity_id=entity_id,
            owner_page_id=f"page:{entity_id}",
            ordinal=int(entity_id),
            name_en=f"name-{entity_id}",
            valuation=f"value-{entity_id}",
            description=f"description-{entity_id}",
            media_binding_tokens=(f"binding:{entity_id}",),
            source_fields={"json_path": token},
        )

    child_a = semantic_child(
        child_id="character:1/alpha:0000",
        parent_id=parent_a.parent_id,
        entity_id="1",
        token="$.alpha",
    )
    child_b = semantic_child(
        child_id="character:2/beta:0000",
        parent_id=parent_b.parent_id,
        entity_id="2",
        token="$.beta",
    )
    projection = SimpleNamespace(
        parents=(parent_b, parent_a),
        children=(child_b, child_a),
    )
    _write_jsonl(
        Path(config["inputs"]["candidate_parents"]["path"]),
        [parent_a.to_json(), parent_b.to_json()],
    )
    _write_jsonl(
        Path(config["inputs"]["candidate_children"]["path"]),
        [child_a.to_json(), child_b.to_json()],
    )

    evidence = _test_evidence_fixture()
    semantic_inputs = SimpleNamespace(
        pages=lambda: (),
        revisions=lambda: (),
        iter_data_page_mappings=lambda: (),
    )
    monkeypatch.setattr(
        module.CrawlerSemanticInputs, "from_root", lambda _root: semantic_inputs
    )
    monkeypatch.setattr(module, "build_page_revision_join", lambda *_args: object())
    monkeypatch.setattr(
        module, "project_crawler_semantics", lambda *_args: evidence.data_projection
    )
    monkeypatch.setattr(
        module, "project_page_semantics", lambda *_args: evidence.page_projection
    )
    monkeypatch.setattr(
        module, "project_topic_semantics", lambda *_args: evidence.topic_projection
    )
    monkeypatch.setattr(module, "compose_corpus_projection", lambda *_args: projection)

    loaded = module.load_validated_evidence(config)

    assert [row["parent_id"] for row in loaded.candidate_parent_rows] == [
        parent_a.parent_id,
        parent_b.parent_id,
    ]
    assert [row["child_id"] for row in loaded.candidate_child_rows] == [
        child_a.block.child_id,
        child_b.block.child_id,
    ]
    assert {
        field: loaded.candidate_child_rows[0][field]
        for field in (
            "stable_source_token",
            "source_token_kind",
            "owner_entity_id",
            "owner_page_id",
            "ordinal",
            "name_en",
            "valuation",
            "description",
            "media_binding_tokens",
            "source_fields",
        )
    } == {
        "stable_source_token": "$.alpha",
        "source_token_kind": "json_path",
        "owner_entity_id": "1",
        "owner_page_id": "page:1",
        "ordinal": 1,
        "name_en": "name-1",
        "valuation": "value-1",
        "description": "description-1",
        "media_binding_tokens": ["binding:1"],
        "source_fields": {"json_path": "$.alpha"},
    }


def test_c8c_reviewed_file_uses_accepted_checkpoint_blob_after_descendant_change(
    tmp_path: Path,
) -> None:
    module = _load_diagnostic()
    config_path, digest, output_root, config = _run_config(
        tmp_path,
        descendant_reviewed_file="src/huiji_rag/build/fidelity.py",
    )
    manifest = json.loads(
        Path(config["inputs"]["c8c_product_manifest"]["path"]).read_bytes()
    )
    reviewed = next(
        identity
        for identity in manifest["inputs"]
        if identity["identity"] == "src/huiji_rag/build/fidelity.py"
    )
    descendant_raw = (
        Path(config["repository_root"]) / reviewed["identity"]
    ).read_bytes()
    assert _sha256(descendant_raw) != reviewed["sha256"]

    loaded = module.load_run_config(
        config_path,
        expected_run_config_sha256=digest,
        output_root=output_root,
    )

    assert loaded == config
    _assert_no_output(output_root)


def test_c8c_reviewed_file_rejects_forged_historical_hash(tmp_path: Path) -> None:
    module = _load_diagnostic()
    _config_path, _digest, _output_root, config = _run_config(tmp_path)
    verified = {
        label: (Path(identity["path"]), Path(identity["path"]).read_bytes())
        for label, identity in config["inputs"].items()
    }
    manifest = json.loads(verified["c8c_product_manifest"][1])
    reviewed = next(
        identity
        for identity in manifest["inputs"]
        if identity["identity"] == "src/huiji_rag/build/fidelity.py"
    )
    reviewed["sha256"] = "0" * 64
    manifest_raw = _canonical_bytes(manifest)
    receipt = json.loads(verified["c8c_product_receipt"][1])
    receipt["output_sha256"]["manifest.product-parity.v1.json"] = _sha256(
        manifest_raw
    )
    receipt_raw = _canonical_bytes(receipt)
    forged = copy.deepcopy(config)
    forged["c8c_evidence_chain"]["manifest_sha256"] = _sha256(manifest_raw)
    forged["c8c_evidence_chain"]["receipt_sha256"] = _sha256(receipt_raw)
    forged_verified = dict(verified)
    forged_verified["c8c_product_manifest"] = (
        verified["c8c_product_manifest"][0],
        manifest_raw,
    )
    forged_verified["c8c_product_receipt"] = (
        verified["c8c_product_receipt"][0],
        receipt_raw,
    )

    with pytest.raises(
        ValueError,
        match="C8c product input identity cross-check mismatch",
    ):
        module._validate_c8c_chain(forged, forged_verified)


@pytest.mark.parametrize("checkpoint_kind", ("missing", "non-ancestor"))
def test_c8c_reviewed_file_rejects_invalid_checkpoint(
    tmp_path: Path,
    checkpoint_kind: str,
) -> None:
    module = _load_diagnostic()
    config_path, _digest, output_root, config = _run_config(tmp_path)
    repository = Path(config["repository_root"])
    if checkpoint_kind == "missing":
        checkpoint = "f" * 40
    else:
        empty_tree = subprocess.run(
            ("git", "hash-object", "-t", "tree", "-w", "--stdin"),
            cwd=repository,
            check=True,
            capture_output=True,
            input=b"",
            shell=False,
        ).stdout.decode("ascii").strip()
        commit_raw = (
            f"tree {empty_tree}\n"
            "author C8d Fixture <c8d@example.invalid> 0 +0000\n"
            "committer C8d Fixture <c8d@example.invalid> 0 +0000\n"
            "\nunrelated checkpoint\n"
        ).encode("utf-8")
        checkpoint = subprocess.run(
            ("git", "hash-object", "-t", "commit", "-w", "--stdin"),
            cwd=repository,
            check=True,
            capture_output=True,
            input=commit_raw,
            shell=False,
        ).stdout.decode("ascii").strip()
    case = copy.deepcopy(config)
    case["accepted_checkpoints"]["c8c_commit"] = checkpoint
    case_raw = _canonical_bytes(case)
    config_path.write_bytes(case_raw)

    with pytest.raises(
        ValueError,
        match="C8c accepted checkpoint Git identity is invalid",
    ):
        module.load_run_config(
            config_path,
            expected_run_config_sha256=_sha256(case_raw),
            output_root=output_root,
        )
    _assert_no_output(output_root)


def test_public_cli_dispatches_hash_pinned_c9_intake_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_diagnostic()
    project_root = tmp_path / "project"
    dependency_root = project_root / "eval/story_segment/dependencies/intake-fixture"
    dependency_root.mkdir(parents=True)
    intake_path = dependency_root / "c9-intake-receipt.v1.json"
    intake_path.write_bytes(b"{}\n")
    digest = _sha256(intake_path.read_bytes())
    output_root = project_root / "eval/story_segment/dependencies/run-fixture/c8d"
    calls: list[tuple[Path, Path, str, Path]] = []

    def capture(
        *,
        project_root: Path,
        c9_intake_path: Path,
        expected_c9_intake_sha256: str,
        output_root: Path,
    ) -> None:
        calls.append(
            (
                Path(project_root),
                Path(c9_intake_path),
                expected_c9_intake_sha256,
                Path(output_root),
            )
        )

    monkeypatch.setattr(module, "run_c9_intake_diagnostic", capture, raising=False)
    argv = [
        "--project-root",
        str(project_root),
        "--c9-intake",
        str(intake_path),
        "--expected-c9-intake-sha256",
        digest,
        "--output-root",
        str(output_root),
        "--read-only",
    ]

    assert module.main(argv) == 0
    assert calls == [(project_root, intake_path, digest, output_root)]


def test_public_entrypoint_is_directly_reachable_with_intake_only_help() -> None:
    completed = subprocess.run(
        (os.sys.executable, "-B", str(SCRIPT), "--help"),
        cwd=SCRIPT.parent.parent,
        capture_output=True,
        text=True,
        shell=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "--project-root" in completed.stdout
    assert "--c9-intake" in completed.stdout
    assert "--expected-c9-intake-sha256" in completed.stdout
    assert "--output-root" in completed.stdout
    assert "--read-only" in completed.stdout
    assert "--run-config" not in completed.stdout


def test_public_cli_rejects_old_run_config_and_requires_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_diagnostic()
    project_root, intake_path, digest, output_root, _intake, _config = _c9_intake(
        tmp_path
    )
    calls: list[object] = []
    monkeypatch.setattr(
        module,
        "run_c9_intake_diagnostic",
        lambda **kwargs: calls.append(kwargs),
    )
    approved = [
        "--project-root",
        str(project_root),
        "--c9-intake",
        str(intake_path),
        "--expected-c9-intake-sha256",
        digest,
        "--output-root",
        str(output_root),
    ]
    old_config_path = tmp_path / "run-config.c8d.json"
    old_config_path.write_bytes(b"{}\n")
    old_argv = [
        "--run-config",
        str(old_config_path),
        "--expected-run-config-sha256",
        _sha256(old_config_path.read_bytes()),
        "--output-root",
        str(output_root),
    ]

    for argv in (approved, old_argv):
        with pytest.raises(SystemExit) as raised:
            module.main(argv)
        assert raised.value.code == 2
        _assert_no_output(output_root)
    assert calls == []


def test_c9_intake_is_the_single_source_for_validated_post_merge_config(
    tmp_path: Path,
) -> None:
    module = _load_diagnostic()
    project_root, intake_path, digest, output_root, intake, old_config = _c9_intake(
        tmp_path
    )

    loaded = module.load_c9_intake(
        project_root=project_root,
        path=intake_path,
        expected_c9_intake_sha256=digest,
        output_root=output_root,
    )

    config = loaded["config"]
    assert config["repository_root"] == project_root.resolve().as_posix()
    assert config["expected_git_head"] == old_config["expected_git_head"]
    assert config["expected_git_tree"] == old_config["expected_git_tree"]
    assert config["accepted_checkpoints"] == old_config["accepted_checkpoints"]
    assert config["expected_output_files"] == list(OUTPUT_NAMES)
    assert set(config["inputs"]) == set(old_config["inputs"])
    assert loaded["authority"] == {
        "path": intake_path.relative_to(project_root).as_posix(),
        "sha256": digest,
        "size_bytes": intake_path.stat().st_size,
        "schema_version": "rag.thread-c9-intake/v1",
    }
    assert loaded["git_identity"] == {
        "head": old_config["expected_git_head"],
        "tree": old_config["expected_git_tree"],
    }
    assert intake["c9_handoff"]["schema_version"] == "huiji.thread-c-c9-audit/v1"
    _assert_no_output(output_root)


def test_c9_intake_runner_names_intake_and_actual_post_merge_git_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_diagnostic()
    project_root, intake_path, digest, output_root, _intake, config = _c9_intake(
        tmp_path
    )
    monkeypatch.setattr(
        module, "load_validated_evidence", lambda _config: _test_evidence_fixture()
    )
    monkeypatch.setattr(
        module, "build_fidelity_ledger", lambda **_kwargs: _fidelity_result()
    )

    module.run_c9_intake_diagnostic(
        project_root=project_root,
        c9_intake_path=intake_path,
        expected_c9_intake_sha256=digest,
        output_root=output_root,
    )

    assert tuple(sorted(path.name for path in output_root.iterdir())) == OUTPUT_NAMES
    manifest = json.loads((output_root / OUTPUT_NAMES[0]).read_bytes())
    receipt = json.loads((output_root / OUTPUT_NAMES[1]).read_bytes())
    expected_authority = {
        "path": intake_path.relative_to(project_root).as_posix(),
        "sha256": digest,
        "size_bytes": intake_path.stat().st_size,
        "schema_version": "rag.thread-c9-intake/v1",
    }
    assert manifest["c9_intake"] == receipt["c9_intake"] == expected_authority
    assert "run_config" not in manifest
    assert manifest["git_identity"] == {
        "head": config["expected_git_head"],
        "tree": config["expected_git_tree"],
    }
    assert receipt["git_identity"] == manifest["git_identity"]
    assert receipt["activity_counters"]["allowed_read_only_git_calls"] == 13
    assert receipt["activity_counters"]["total_subprocess_calls"] == 13
    assert all(
        count == 0
        for name, count in receipt["activity_counters"].items()
        if name not in {"allowed_read_only_git_calls", "total_subprocess_calls"}
    )


@pytest.mark.parametrize(
    "case",
    (
        "tampered-bytes",
        "duplicate-key",
        "extra-field",
        "missing-field",
        "path-escape",
        "missing-input",
        "entrypoint-hash",
        "entrypoint-schema",
        "handoff-hash",
        "handoff-schema",
        "input-hash",
        "input-size",
        "input-row-count",
        "protected-count",
        "canonical-outputs",
    ),
)
def test_c9_intake_preflight_rejects_invalid_authority_without_output(
    tmp_path: Path, case: str
) -> None:
    module = _load_diagnostic()
    project_root, intake_path, digest, output_root, intake, _config = _c9_intake(
        tmp_path
    )
    payload = copy.deepcopy(intake)
    expected_digest = digest
    if case == "tampered-bytes":
        raw = intake_path.read_bytes() + b" "
    elif case == "duplicate-key":
        raw = (
            b'{"schema_version":"duplicate",'
            + intake_path.read_bytes().lstrip()[1:]
        )
        expected_digest = _sha256(raw)
    else:
        if case == "extra-field":
            payload["unexpected"] = True
        elif case == "missing-field":
            payload.pop("c8c_evidence_chain")
        elif case == "path-escape":
            payload["inputs"]["active_parents"]["relative_path"] = "../escape.jsonl"
        elif case == "missing-input":
            payload["inputs"]["active_parents"]["relative_path"] = (
                "missing/parents.jsonl"
            )
        elif case == "entrypoint-hash":
            payload["c8d_entrypoint"]["sha256"] = "0" * 64
        elif case == "entrypoint-schema":
            payload["c8d_entrypoint"]["schema_version"] = "wrong"
        elif case == "handoff-hash":
            payload["c9_handoff"]["sha256"] = "0" * 64
        elif case == "handoff-schema":
            payload["c9_handoff"]["schema_version"] = "wrong"
        elif case == "input-hash":
            payload["inputs"]["active_parents"]["sha256"] = "0" * 64
        elif case == "input-size":
            payload["inputs"]["active_parents"]["size_bytes"] += 1
        elif case == "input-row-count":
            payload["inputs"]["active_parents"]["row_count"] += 1
        elif case == "protected-count":
            payload["expected_protected_identity_count"] += 1
        elif case == "canonical-outputs":
            payload["expected_output_files"] = list(reversed(OUTPUT_NAMES))
        raw = _canonical_bytes(payload)
        expected_digest = _sha256(raw)
    intake_path.write_bytes(raw)

    with pytest.raises((OSError, RuntimeError, ValueError)):
        module.load_c9_intake(
            project_root=project_root,
            path=intake_path,
            expected_c9_intake_sha256=expected_digest,
            output_root=output_root,
        )
    _assert_no_output(output_root)


def test_c9_intake_rejects_nonancestor_checkpoint_without_output(
    tmp_path: Path,
) -> None:
    module = _load_diagnostic()
    project_root, intake_path, _digest, output_root, intake, _config = _c9_intake(
        tmp_path
    )
    payload = copy.deepcopy(intake)
    payload["release_checkpoints"]["c9_commit"] = DESCENDANT_HEAD
    payload["release_checkpoints"]["c9_tree"] = DESCENDANT_TREE
    handoff_path = project_root / payload["c9_handoff"]["relative_path"]
    handoff = json.loads(handoff_path.read_bytes())
    handoff["git_identity"]["head"] = DESCENDANT_HEAD
    handoff["git_identity"]["tree"] = DESCENDANT_TREE
    handoff["commit_chain"]["head_inclusive"] = DESCENDANT_HEAD
    handoff_raw = _canonical_bytes(handoff)
    handoff_path.write_bytes(handoff_raw)
    payload["c9_handoff"]["sha256"] = _sha256(handoff_raw)
    payload["c9_handoff"]["size_bytes"] = len(handoff_raw)
    raw = _canonical_bytes(payload)
    intake_path.write_bytes(raw)

    with pytest.raises(ValueError, match="not an ancestor"):
        module.load_c9_intake(
            project_root=project_root,
            path=intake_path,
            expected_c9_intake_sha256=_sha256(raw),
            output_root=output_root,
        )
    _assert_no_output(output_root)


def test_c9_intake_rejects_intermediate_commit_between_c8d_and_c9(
    tmp_path: Path,
) -> None:
    module = _load_diagnostic()
    project_root, intake_path, _digest, output_root, intake, _config = _c9_intake(
        tmp_path
    )
    c8d_commit = intake["release_checkpoints"]["c8d_commit"]
    tree = intake["release_checkpoints"]["c9_tree"]
    intermediate = _commit_tree(project_root, tree, c8d_commit, "intermediate")
    c9_commit = _commit_tree(project_root, tree, intermediate, "not direct C9")
    runtime_head = _commit_tree(project_root, tree, c9_commit, "runtime descendant")
    subprocess.run(
        ("git", "update-ref", "refs/heads/main", runtime_head),
        cwd=project_root,
        check=True,
        capture_output=True,
        shell=False,
    )
    intake["release_checkpoints"]["c9_commit"] = c9_commit

    def update_handoff(handoff: dict[str, object]) -> None:
        handoff["git_identity"].update(
            {"head": c9_commit, "tree": tree, "parent": c8d_commit}
        )
        handoff["commit_chain"]["head_inclusive"] = c9_commit

    digest = _rewrite_handoff_and_intake(
        project_root, intake_path, intake, update_handoff
    )

    with pytest.raises(ValueError, match="direct parent"):
        module.load_c9_intake(
            project_root=project_root,
            path=intake_path,
            expected_c9_intake_sha256=digest,
            output_root=output_root,
        )
    _assert_no_output(output_root)


def test_c9_intake_rejects_nonzero_checkpoint_tree_diff_without_output(
    tmp_path: Path,
) -> None:
    module = _load_diagnostic()
    project_root, intake_path, _digest, output_root, intake, _config = _c9_intake(
        tmp_path
    )
    c8d_commit = intake["release_checkpoints"]["c8d_commit"]
    changed_tree = subprocess.run(
        ("git", "rev-parse", f"{C8C_COMMIT}^{{tree}}"),
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
        shell=False,
    ).stdout.strip()
    assert changed_tree != intake["release_checkpoints"]["c9_tree"]
    c9_commit = _commit_tree(project_root, changed_tree, c8d_commit, "changed C9")
    runtime_head = _commit_tree(
        project_root, changed_tree, c9_commit, "runtime descendant"
    )
    subprocess.run(
        ("git", "update-ref", "refs/heads/main", runtime_head),
        cwd=project_root,
        check=True,
        capture_output=True,
        shell=False,
    )
    intake["release_checkpoints"].update(
        {"c9_commit": c9_commit, "c9_tree": changed_tree}
    )

    def update_handoff(handoff: dict[str, object]) -> None:
        handoff["git_identity"].update(
            {"head": c9_commit, "tree": changed_tree, "parent": c8d_commit}
        )
        handoff["commit_chain"]["head_inclusive"] = c9_commit

    digest = _rewrite_handoff_and_intake(
        project_root, intake_path, intake, update_handoff
    )

    with pytest.raises(ValueError, match="zero tracked diff"):
        module.load_c9_intake(
            project_root=project_root,
            path=intake_path,
            expected_c9_intake_sha256=digest,
            output_root=output_root,
        )
    _assert_no_output(output_root)


@pytest.mark.parametrize(
    "field",
    (
        "head",
        "tree",
        "parent",
        "checkpoint_parent_tracked_diff_empty",
        "head_inclusive",
    ),
)
def test_c9_intake_rejects_forged_handoff_git_identity_without_output(
    tmp_path: Path, field: str
) -> None:
    module = _load_diagnostic()
    project_root, intake_path, _digest, output_root, intake, _config = _c9_intake(
        tmp_path
    )

    def forge(handoff: dict[str, object]) -> None:
        if field == "head_inclusive":
            handoff["commit_chain"][field] = "0" * 40
        elif field == "checkpoint_parent_tracked_diff_empty":
            handoff["git_identity"][field] = False
        else:
            handoff["git_identity"][field] = "0" * 40

    digest = _rewrite_handoff_and_intake(project_root, intake_path, intake, forge)

    with pytest.raises(ValueError, match="handoff"):
        module.load_c9_intake(
            project_root=project_root,
            path=intake_path,
            expected_c9_intake_sha256=digest,
            output_root=output_root,
        )
    _assert_no_output(output_root)


@pytest.mark.parametrize(
    "case",
    (
        "deterministic-gate",
        "candidate-cli-blocker",
        "deterministic-blocker",
        "ownership-clean",
        "forbidden-runtime-diff",
        "external-performed",
        "external-count",
        "external-count-type",
        "external-counts-missing",
        "ownership-structure-type",
        "newly-tracked-forbidden",
        "newly-tracked-type",
        "vector-owner",
    ),
)
def test_c9_intake_rejects_false_or_malformed_handoff_safety_gate(
    tmp_path: Path, case: str
) -> None:
    module = _load_diagnostic()
    project_root, intake_path, _digest, output_root, intake, _config = _c9_intake(
        tmp_path
    )

    def break_gate(handoff: dict[str, object]) -> None:
        if case == "deterministic-gate":
            handoff["deterministic_closure"]["gate_closed"] = False
        elif case == "candidate-cli-blocker":
            handoff["remaining_blocker_classification"][
                "unresolved_candidate_cli_blocker"
            ] = True
        elif case == "deterministic-blocker":
            handoff["remaining_blocker_classification"][
                "unresolved_deterministic_closure_blocker"
            ] = True
        elif case == "ownership-clean":
            handoff["ownership_audit"]["tracked_worktree_clean"] = False
        elif case == "forbidden-runtime-diff":
            handoff["ownership_audit"]["forbidden_ab_runtime_diff_empty"] = False
        elif case == "external-performed":
            handoff["ownership_audit"]["external_operation_performed"] = True
        elif case == "external-count":
            handoff["ownership_audit"]["external_operation_counts"]["network"] = 1
        elif case == "external-count-type":
            handoff["ownership_audit"]["external_operation_counts"]["network"] = False
        elif case == "external-counts-missing":
            handoff["ownership_audit"].pop("external_operation_counts")
        elif case == "ownership-structure-type":
            handoff["ownership_audit"] = []
        elif case == "newly-tracked-forbidden":
            handoff["ownership_audit"]["newly_tracked_forbidden_artifacts"][
                "raw_snapshot"
            ] = True
        elif case == "newly-tracked-type":
            handoff["ownership_audit"]["newly_tracked_forbidden_artifacts"][
                "raw_snapshot"
            ] = 0
        elif case == "vector-owner":
            handoff["vector_rebuild_disposition"]["decision_owner"] = "C"

    digest = _rewrite_handoff_and_intake(
        project_root, intake_path, intake, break_gate
    )

    with pytest.raises(ValueError, match="handoff"):
        module.load_c9_intake(
            project_root=project_root,
            path=intake_path,
            expected_c9_intake_sha256=digest,
            output_root=output_root,
        )
    _assert_no_output(output_root)


@pytest.mark.parametrize("escape_kind", ("project", "output"))
def test_c9_intake_rejects_project_or_output_confinement_without_output(
    tmp_path: Path, escape_kind: str
) -> None:
    module = _load_diagnostic()
    project_root, intake_path, digest, output_root, _intake, _config = _c9_intake(
        tmp_path
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    supplied_project = outside if escape_kind == "project" else project_root
    supplied_output = outside / "c8d" if escape_kind == "output" else output_root

    with pytest.raises((OSError, ValueError)):
        module.load_c9_intake(
            project_root=supplied_project,
            path=intake_path,
            expected_c9_intake_sha256=digest,
            output_root=supplied_output,
        )
    _assert_no_output(supplied_output)


def test_c9_intake_rejects_symlinked_input_without_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_diagnostic()
    project_root, intake_path, _digest, output_root, intake, _config = _c9_intake(
        tmp_path
    )
    target = project_root / intake["inputs"]["active_parents"]["relative_path"]
    link = target.with_name("linked-parents.jsonl")
    original_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda self: self == link or original_is_symlink(self),
    )
    payload = copy.deepcopy(intake)
    payload["inputs"]["active_parents"]["relative_path"] = (
        link.relative_to(project_root).as_posix()
    )
    raw = _canonical_bytes(payload)
    intake_path.write_bytes(raw)

    with pytest.raises(ValueError, match="symlink"):
        module.load_c9_intake(
            project_root=project_root,
            path=intake_path,
            expected_c9_intake_sha256=_sha256(raw),
            output_root=output_root,
        )
    _assert_no_output(output_root)


def test_internal_run_config_preserves_exact_identity_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_diagnostic()
    config_path, digest, output_root, config = _run_config(tmp_path)
    assert set(config) == {
        "schema_version",
        "run_id",
        "repository_root",
        "protected_state_root",
        "output_root",
        "expected_git_head",
        "expected_git_tree",
        "diagnostic",
        "accepted_checkpoints",
        "expected_output_files",
        "sample_limit_per_blocker_prefix",
        "expected_protected_identity_count",
        "expected_protected_drift_count",
        "expected_legacy_media_category_counts",
        "inputs",
        "c8c_evidence_chain",
    }
    assert config["expected_git_head"] == HEAD
    assert config["accepted_checkpoints"]["c8c_commit"] == C8C_COMMIT
    assert C8C_COMMIT != HEAD
    repository_root = Path(config["repository_root"]).resolve()
    protected_state_root = Path(config["protected_state_root"]).resolve()
    assert protected_state_root.is_dir()
    assert not protected_state_root.is_symlink()
    assert not protected_state_root.is_relative_to(repository_root)
    verified = {
        label: (Path(identity["path"]), Path(identity["path"]).read_bytes())
        for label, identity in config["inputs"].items()
    }
    taxonomy = json.loads(verified["c8c_taxonomy"][1])
    product_manifest = json.loads(verified["c8c_product_manifest"][1])
    accepted_taxonomy_witness = next(
        identity
        for identity in product_manifest["inputs"]
        if identity["label"] == "accepted_taxonomy"
    )
    protected_identity_manifest_witness = next(
        identity
        for identity in product_manifest["inputs"]
        if identity["label"] == "protected_identity_manifest"
    )
    assert "row_count" not in config["inputs"]["c8c_taxonomy"]
    assert accepted_taxonomy_witness["row_count"] == len(taxonomy["rows"]) == 6
    assert "row_count" not in config["inputs"]["protected_identity_manifest"]
    assert protected_identity_manifest_witness["row_count"] == 32
    active_media_rows = [
        json.loads(line)
        for line in verified["active_media"][1].decode("utf-8").splitlines()
    ]
    assert {
        row["legacy_row_sha256"] for row in taxonomy["rows"]
    } == {
        _sha256(
            _canonical_json_bytes(row, trailing_newline=False)
        )
        for row in active_media_rows
    }
    assert all(
        row["legacy_row_sha256"]
        != _sha256(_canonical_bytes(active))
        for row, active in zip(
            taxonomy["rows"], active_media_rows, strict=True
        )
    )
    assert set(taxonomy["coverage_checks"]) == {
        "all_categories_known",
        "category_sum_equals_active_occurrence_count",
        "each_active_occurrence_exactly_once",
        "incomplete_evidence_explicit_count",
        "potential_candidate_collision_count",
        "proven_candidate_consumption_collision_count",
    }
    assert set(taxonomy["duplicate_consumption_checks"]) == {
        "bounded_collision_samples",
        "duplicate_active_occurrence_id_count",
        "potential_candidate_collision_count",
        "proven_candidate_consumption_collision_count",
    }
    assert set(taxonomy["population_cross_check"]) == {
        "accepted_baseline",
        "accepted_fidelity_active_occurrences",
        "accepted_fidelity_unexplained_binding_loss",
        "legacy_jsonl",
        "pinned_expected_result",
    }
    assert set(taxonomy["population_cross_check"].values()) == {
        len(active_media_rows)
    }
    assert (
        taxonomy["coverage_checks"][
            "proven_candidate_consumption_collision_count"
        ]
        == taxonomy["duplicate_consumption_checks"][
            "proven_candidate_consumption_collision_count"
        ]
        == 0
    )
    ambiguous_rows = [
        row
        for row in taxonomy["rows"]
        if row["category"] == "ambiguous_binding"
    ]
    assert len(ambiguous_rows) == 2
    assert (
        ambiguous_rows[0]["potential_candidate_ids"]
        == ambiguous_rows[1]["potential_candidate_ids"]
    )
    candidate_media_by_id = {
        row["binding_id"]: row
        for row in (
            json.loads(line)
            for line in verified["candidate_media_v3"][1]
            .decode("utf-8")
            .splitlines()
        )
    }
    for row in taxonomy["rows"]:
        expected_source_ids = {
            _source_binding_token_id(
                candidate_media_by_id[candidate_id][
                    "source_binding_token"
                ]
            )
            for candidate_id in row["candidate_binding_ids"]
        }
        assert set(row["candidate_source_binding_token_ids"]) == (
            expected_source_ids
        )
        assert all(
            stable_id
            != candidate_media_by_id[candidate_id][
                "source_binding_token"
            ]
            for stable_id in row["candidate_source_binding_token_ids"]
            for candidate_id in row["candidate_binding_ids"]
        )

    module._validate_c8c_chain(config, verified)

    field_drift_taxonomy = copy.deepcopy(taxonomy)
    field_drift_taxonomy["coverage_checks"][
        "category_sum_matches_population"
    ] = field_drift_taxonomy["coverage_checks"].pop(
        "category_sum_equals_active_occurrence_count"
    )
    field_drift_verified = dict(verified)
    field_drift_verified["c8c_taxonomy"] = (
        verified["c8c_taxonomy"][0],
        _canonical_bytes(field_drift_taxonomy),
    )
    with pytest.raises(ValueError):
        module._validate_c8c_chain(config, field_drift_verified)

    product_chain_mismatch = copy.deepcopy(config)
    product_chain_mismatch["c8c_evidence_chain"][
        "occurrence_ledger_sha256"
    ] = "0" * 64
    with pytest.raises(ValueError, match="occurrence ledger"):
        module._validate_c8c_chain(product_chain_mismatch, verified)

    # Let this node isolate the frozen checkpoint-equality defect instead of
    # stopping first at the newly required top-level protected-root field.
    monkeypatch.setattr(
        module,
        "_TOP_LEVEL_FIELDS",
        {*module._TOP_LEVEL_FIELDS, "protected_state_root"},
    )
    loaded = module.load_run_config(
        config_path, expected_run_config_sha256=digest, output_root=output_root
    )
    assert loaded == config
    wrong_path, wrong_digest, wrong_output, _wrong_config = _run_config(
        tmp_path / "wrong-taxonomy-row-count",
        accepted_taxonomy_manifest_row_count=5,
    )
    with pytest.raises(ValueError, match="product input identity cross-check"):
        module.load_run_config(
            wrong_path,
            expected_run_config_sha256=wrong_digest,
            output_root=wrong_output,
        )
    (
        wrong_protected_path,
        wrong_protected_digest,
        wrong_protected_output,
        _wrong_protected_config,
    ) = _run_config(
        tmp_path / "wrong-protected-identity-manifest-row-count",
        protected_identity_manifest_row_count=31,
    )
    with pytest.raises(ValueError, match="product input identity cross-check"):
        module.load_run_config(
            wrong_protected_path,
            expected_run_config_sha256=wrong_protected_digest,
            output_root=wrong_protected_output,
        )
    assert C8B_EVIDENCE_MANIFEST_SHA256 == "977cde250ec88e970150ce98d97339f17555639dbcf905154ffd4c9a283e5fc0"
    assert C8B_TAXONOMY_SHA256 == "44a511ba41a7067e4536c51226c8c40603c55806653a22bde468be066ac32ecd"
    assert C8C_PRODUCT_MANIFEST_SHA256 == "dc7dc31936c8e85d6c6f3af5a10c1eeb9a70300ac9990476d8f27bb1b164e764"
    assert PROTECTED_STATE_SHA256 == "ef85f54d229e05d975092badfd734899e85c6a74d30f0cac310b8b0d0a4b355f"
    assert loaded["accepted_checkpoints"] == config["accepted_checkpoints"]
    assert set(loaded["inputs"]) >= {
        "protected_identity_manifest",
        "crawler_pages",
        "crawler_wikitext",
        "crawler_data_pages",
        "crawler_resources_manifest",
        "c8b_taxonomy",
        "c8c_taxonomy",
        "c8c_product_manifest",
        "c8c_product_summary",
        "c8c_product_receipt",
    }
    assert "c8b_story_ledger" in loaded["inputs"]
    for identity in loaded["inputs"].values():
        path = Path(identity["path"])
        raw = path.read_bytes()
        assert path.is_file()
        assert len(raw) == identity["size_bytes"]
        assert _sha256(raw) == identity["sha256"]
        if "row_count" in identity:
            assert raw.count(b"\n") == identity["row_count"]
    for name in ("c8b_d_acceptance", "c8c_d_acceptance"):
        identity = loaded["accepted_checkpoints"][name]
        raw = Path(identity["path"]).read_bytes()
        assert len(raw) == identity["size_bytes"]
        assert _sha256(raw) == identity["sha256"]
    diagnostic_path = (
        Path(loaded["repository_root"]) / loaded["diagnostic"]["path"]
    )
    assert _sha256(diagnostic_path.read_bytes()) == loaded["diagnostic"]["sha256"]
    for label in ("active_child_bm25", "active_media_bm25"):
        payload = json.loads(Path(loaded["inputs"][label]["path"]).read_bytes())
        assert set(payload) == {"records"}
        assert isinstance(payload["records"], list)
    protected = json.loads(
        Path(loaded["inputs"]["protected_identity_manifest"]["path"]).read_bytes()
    )
    assert protected["schema_version"] == "huiji.task8-protected-state/v1"
    assert len(protected["records"]) == 32
    assert all(
        set(record) == {"label", "path", "sha256", "size", "mtime_ns"}
        for record in protected["records"]
    )
    assert all(
        Path(record["path"]).resolve().is_relative_to(protected_state_root)
        for record in protected["records"]
    )
    assert all(
        not Path(record["path"]).resolve().is_relative_to(repository_root)
        for record in protected["records"]
    )
    c8b_taxonomy = json.loads(
        Path(loaded["inputs"]["c8b_taxonomy"]["path"]).read_bytes()
    )
    assert set(c8b_taxonomy) == {
        "decision_matrix",
        "dynamic_counts",
        "inputs",
        "mode",
        "one_to_one_migration_pair_audit",
        "policy_selection",
        "run",
        "safety",
        "samples",
        "schema_version",
        "stage_metrics",
        "status",
        "story_record_link_evidence",
        "taxonomy",
    }
    assert c8b_taxonomy["schema_version"] == (
        "huiji.task8-c8b-story-legacy-taxonomy/v1"
    )
    assert set(c8b_taxonomy["story_record_link_evidence"]) == {
        "parent",
        "child",
        "missing_record_link_causes",
    }
    assert set(c8b_taxonomy["story_record_link_evidence"]["parent"]) == {
        "candidate_count",
        "missing_record_link_count",
        "new_source_record_link_count",
        "source_ref_complete_count",
    }
    assert set(c8b_taxonomy["story_record_link_evidence"]["child"]) == {
        "candidate_count",
        "missing_record_link_count",
        "new_source_record_link_count",
        "source_ref_complete_count",
        "stable_source_token_kind_counts",
    }
    missing_causes = c8b_taxonomy["story_record_link_evidence"][
        "missing_record_link_causes"
    ]
    assert isinstance(missing_causes, list) and len(missing_causes) == 3
    assert all(
        set(row)
        == {"observed_behavior", "record_kind", "source_function", "source_stage"}
        for row in missing_causes
    )
    assert "ledger_id" not in json.dumps(c8b_taxonomy)
    c8b_manifest_path = Path(loaded["inputs"]["c8b_taxonomy"]["path"]).with_name(
        "manifest.c8b3.v1.json"
    )
    c8b_manifest = json.loads(c8b_manifest_path.read_bytes())
    assert set(c8b_manifest) == {
        "checkpoint_commit",
        "files",
        "protected_drift_count",
        "protected_identity_count",
        "run_id",
        "schema_version",
        "status",
    }
    assert c8b_manifest["schema_version"] == "huiji.task8-c8b-evidence-manifest/v1"
    assert c8b_manifest["checkpoint_commit"] == C8A_COMMIT
    assert c8b_manifest["run_id"] == "task8-c-20260729T161119Z"
    assert c8b_manifest["status"] == "completed_pending_review"
    assert c8b_manifest["protected_identity_count"] == 32
    assert c8b_manifest["protected_drift_count"] == 0
    assert isinstance(c8b_manifest["files"], list)
    assert [entry["basename"] for entry in c8b_manifest["files"]] == [
        "taxonomy.py",
        "protected_pre.c8b3.v1.json",
        "taxonomy.c8b3.v1.json",
        "protected_post.c8b3.v1.json",
        "protected_compare.c8b3.v1.json",
    ]
    assert all(
        set(entry) == {"basename", "label", "mtime_ns", "sha256", "size"}
        for entry in c8b_manifest["files"]
    )
    for entry in c8b_manifest["files"]:
        witness_path = c8b_manifest_path.with_name(entry["basename"])
        witness_raw = witness_path.read_bytes()
        assert witness_path.stat().st_mtime_ns == entry["mtime_ns"]
        assert _sha256(witness_raw) == entry["sha256"]
        assert len(witness_raw) == entry["size"]
    taxonomy_entries = [
        entry
        for entry in c8b_manifest["files"]
        if entry["basename"] == entry["label"] == "taxonomy.c8b3.v1.json"
    ]
    assert taxonomy_entries == [{
        "basename": "taxonomy.c8b3.v1.json",
        "label": "taxonomy.c8b3.v1.json",
        "mtime_ns": Path(loaded["inputs"]["c8b_taxonomy"]["path"]).stat().st_mtime_ns,
        "sha256": loaded["inputs"]["c8b_taxonomy"]["sha256"],
        "size": loaded["inputs"]["c8b_taxonomy"]["size_bytes"],
    }]
    story_ledger_rows = [
        json.loads(line)
        for line in Path(loaded["inputs"]["c8b_story_ledger"]["path"])
        .read_text()
        .splitlines()
    ]
    assert story_ledger_rows[0]["source_evidence"] == _story_ledger_row()[
        "source_evidence"
    ]
    assert story_ledger_rows[1]["active_identity"] == _active_non_story_child()[
        "record_id"
    ]
    assert story_ledger_rows[1]["candidate_identities"] == [
        _candidate_non_story_child()["record_id"]
    ]

    resource_identity = loaded["inputs"]["resource_metadata"]
    assert resource_identity == loaded["inputs"]["crawler_resources_manifest"]
    resource_rows = [
        json.loads(line)
        for line in Path(resource_identity["path"]).read_text().splitlines()
    ]
    assert all(
        set(row)
        == {
            "descriptionurl",
            "download_status",
            "height",
            "local_relpath",
            "mime",
            "name",
            "seen_at",
            "sha1",
            "site",
            "size",
            "source",
            "timestamp",
            "title",
            "url",
            "width",
        }
        for row in resource_rows
    )
    candidate_media_rows = [
        json.loads(line)
        for line in Path(loaded["inputs"]["candidate_media_v3"]["path"])
        .read_text()
        .splitlines()
    ]
    required_media_fields = {
        "binding_id",
        "resource_id",
        "source_sha1",
        "content_sha256",
        "content_hash",
        "size",
        "filename",
        "title",
    }
    assert all(required_media_fields <= set(row) for row in candidate_media_rows)
    forbidden_resource_fields = {
        "resource_sha1",
        "resource_sha256",
        "resource_size",
        "size_bytes",
    }
    assert all(not forbidden_resource_fields.intersection(row) for row in candidate_media_rows)
    assert all("resource_id" not in row for row in resource_rows)
    candidate_resource_matches = {
        candidate["binding_id"]: [
            resource
            for resource in resource_rows
            if (
                candidate["source_sha1"],
                candidate["filename"],
                candidate["size"],
            )
            == (
                resource["sha1"],
                resource["name"],
                resource["size"],
            )
        ]
        for candidate in candidate_media_rows
    }
    assert all(
        len(matches) == 1
        for matches in candidate_resource_matches.values()
    )
    assert all(
        candidate["title"]
        != candidate_resource_matches[candidate["binding_id"]][0][
            "title"
        ]
        for candidate in candidate_media_rows
    )
    assert {
        row["sha1"] for row in resource_rows
    } > {
        row["source_sha1"] for row in candidate_media_rows
    }
    repeated_sha1_resources = [
        row
        for row in resource_rows
        if row["sha1"] == candidate_media_rows[0]["source_sha1"]
    ]
    assert len(repeated_sha1_resources) == 2
    assert len(
        {
            (row["name"], row["size"])
            for row in repeated_sha1_resources
        }
    ) == 2

    product_manifest = json.loads(
        Path(loaded["inputs"]["c8c_product_manifest"]["path"]).read_bytes()
    )
    product_summary_path = Path(
        loaded["inputs"]["c8c_product_summary"]["path"]
    )
    product_summary = json.loads(product_summary_path.read_bytes())
    product_receipt = json.loads(
        Path(loaded["inputs"]["c8c_product_receipt"]["path"]).read_bytes()
    )
    c8c_taxonomy = json.loads(
        Path(loaded["inputs"]["c8c_taxonomy"]["path"]).read_bytes()
    )
    assert c8c_taxonomy["active_occurrence_count"] == len(c8c_taxonomy["rows"]) == 6
    assert sum(c8c_taxonomy["category_counts"].values()) == 6
    assert c8c_taxonomy["category_counts"] == MEDIA_COUNTS
    assert product_summary["accepted_taxonomy"] == {
        "active_occurrence_count": 6,
        "category_counts": MEDIA_COUNTS,
        "unexplained_binding_loss": 6,
    }
    assert set(product_manifest) == {
        "diagnostic_script_sha256",
        "forbidden_action_counters",
        "head",
        "inputs",
        "interpreter",
        "outputs",
        "protected_drift_count",
        "protected_identity_count",
        "run_id",
        "schema_version",
        "status",
        "tree",
    }
    assert all(
        set(identity) == {"identity", "label", "row_count", "sha256", "size"}
        for identity in product_manifest["inputs"]
    )
    assert [entry["label"] for entry in product_manifest["inputs"]] == [
        "d_acceptance_receipt",
        "d_green_review_receipt",
        "legacy_active_media",
        "accepted_taxonomy",
        "candidate_media_v3",
        "accepted_baseline",
        "protected_identity_manifest",
        "pages",
        "wikitext",
        "data_pages",
        "resources_manifest",
        "reviewed_file",
        "reviewed_file",
        "reviewed_file",
        "reviewed_file",
        "reviewed_file",
        "reviewed_file",
    ]
    accepted_baseline_entry = next(
        entry
        for entry in product_manifest["inputs"]
        if entry["label"] == "accepted_baseline"
    )
    assert accepted_baseline_entry["identity"] == (
        "eval/huiji_corpus_fidelity/20260720T073917Z/"
        "corpus-preservation-baseline.v2.json"
    )
    accepted_baseline_path = (
        Path(loaded["repository_root"]) / accepted_baseline_entry["identity"]
    )
    bm25_identities = tuple(
        loaded["inputs"][label]
        for label in ("active_child_bm25", "active_media_bm25")
    )
    assert all(
        accepted_baseline_entry["identity"]
        != Path(identity["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix()
        for identity in bm25_identities
    )
    assert all(
        accepted_baseline_path != Path(identity["path"])
        for identity in bm25_identities
    )
    assert all(
        accepted_baseline_entry["sha256"] != identity["sha256"]
        for identity in bm25_identities
    )
    accepted_baseline_payload = json.loads(accepted_baseline_path.read_bytes())
    assert accepted_baseline_payload["schema_version"] == (
        "huiji.corpus-preservation-baseline/v2"
    )
    assert accepted_baseline_payload["status"] == "pass"
    assert [entry["identity"] for entry in product_manifest["inputs"]] == [
        ".codex-supervisor/workers/C/d-review-c8c-real-interface-accepted.json",
        ".codex-supervisor/workers/C/d-review-c8c-final-43-green.json",
        Path(loaded["inputs"]["active_media"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        Path(loaded["inputs"]["c8c_taxonomy"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        Path(loaded["inputs"]["candidate_media_v3"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        "eval/huiji_corpus_fidelity/20260720T073917Z/"
        "corpus-preservation-baseline.v2.json",
        Path(loaded["inputs"]["protected_identity_manifest"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        Path(loaded["inputs"]["crawler_pages"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        Path(loaded["inputs"]["crawler_wikitext"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        Path(loaded["inputs"]["crawler_data_pages"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        Path(loaded["inputs"]["crawler_resources_manifest"]["path"])
        .relative_to(Path(loaded["repository_root"]))
        .as_posix(),
        "src/huiji_rag/build/media_v3.py",
        "src/huiji_rag/build/fidelity.py",
        "src/huiji_rag/build/orchestrator.py",
        "tests/test_huiji_media_v3_builder.py",
        "tests/test_huiji_corpus_fidelity.py",
        "docs/superpowers/specs/2026-07-29-rag-thread-c-legacy-media-decision.md",
    ]
    for entry in product_manifest["inputs"]:
        witness_raw = (Path(loaded["repository_root"]) / entry["identity"]).read_bytes()
        assert _sha256(witness_raw) == entry["sha256"]
        assert len(witness_raw) == entry["size"]
    assert len(product_manifest["inputs"]) == len(
        {entry["identity"] for entry in product_manifest["inputs"]}
    )
    assert set(product_summary) == {
        "accepted_taxonomy",
        "active_occurrence_count",
        "category_counts",
        "elapsed_seconds",
        "fidelity",
        "forbidden_action_counters",
        "head",
        "observed_audit_events",
        "parity",
        "peak_rss_bytes",
        "product_interface",
        "product_occurrence_ledger_sha256",
        "protected_state",
        "run_id",
        "schema_version",
        "stage_elapsed_seconds",
        "status",
        "tree",
        "unexplained_binding_loss",
    }
    assert set(product_receipt) == {
        "active_occurrence_count",
        "category_counts",
        "commit_created",
        "forbidden_action_counters",
        "head",
        "output_sha256",
        "protected_drift_count",
        "protected_identity_count",
        "run_id",
        "schema_version",
        "staged_path_count",
        "status",
        "tracked_files_modified",
        "tree",
        "unexplained_binding_loss",
    }
    assert (
        product_manifest["outputs"]["summary.product-parity.v1.json"]
        == _sha256(product_summary_path.read_bytes())
        == product_receipt["output_sha256"]["summary.product-parity.v1.json"]
    )
    product_manifest_path = Path(
        loaded["inputs"]["c8c_product_manifest"]["path"]
    )
    assert (
        product_receipt["output_sha256"]["manifest.product-parity.v1.json"]
        == _sha256(product_manifest_path.read_bytes())
    )
    product_diagnostic_path = product_manifest_path.with_name(
        "diagnostic.product-parity.py"
    )
    assert (
        product_manifest["diagnostic_script_sha256"]
        == _sha256(product_diagnostic_path.read_bytes())
        == product_receipt["output_sha256"]["diagnostic.product-parity.py"]
    )
    assert product_manifest["run_id"] == product_summary["run_id"]
    assert product_manifest["run_id"] == product_receipt["run_id"]
    assert product_manifest["head"] == product_summary["head"] == product_receipt["head"]
    assert product_manifest["tree"] == product_summary["tree"] == product_receipt["tree"]
    assert (
        product_summary["product_occurrence_ledger_sha256"]
        == loaded["c8c_evidence_chain"]["occurrence_ledger_sha256"]
    )
    assert product_summary[
        "product_occurrence_ledger_sha256"
    ] != _sha256(_canonical_bytes(c8c_taxonomy["rows"]))


def test_diagnostic_calls_full_fidelity_and_separates_blocker_classes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_diagnostic()
    config_path, digest, output_root, config = _run_config(tmp_path)
    # Isolate the frozen protected-record containment defect. The ordinary
    # invocation below retains the truthful distinct C8c/C8d identities.
    monkeypatch.setattr(
        module,
        "_TOP_LEVEL_FIELDS",
        {*module._TOP_LEVEL_FIELDS, "protected_state_root"},
    )
    protected_root_probe = copy.deepcopy(config)
    protected_root_probe["accepted_checkpoints"]["c8c_commit"] = HEAD
    protected_root_probe_path = tmp_path / "protected-root-probe.c8d.json"
    protected_root_probe_raw = _canonical_bytes(protected_root_probe)
    protected_root_probe_path.write_bytes(protected_root_probe_raw)
    assert module.load_run_config(
        protected_root_probe_path,
        expected_run_config_sha256=_sha256(protected_root_probe_raw),
        output_root=output_root,
    ) == protected_root_probe
    evidence = _test_evidence_fixture()
    candidate_parent_rows = (
        {**_candidate_parent(), "parent_id": _candidate_parent()["record_id"]},
    )
    candidate_child_rows = tuple(
        sorted(
            (
                {**row, "child_id": row["record_id"]}
                for row in (
                    _candidate_child(0),
                    _candidate_child(1),
                    _candidate_non_story_child(),
                )
            ),
            key=lambda row: str(row["child_id"]),
        )
    )
    config["inputs"]["candidate_parents"] = _write_jsonl(
        Path(config["inputs"]["candidate_parents"]["path"]),
        list(candidate_parent_rows),
    )
    config["inputs"]["candidate_children"] = _write_jsonl(
        Path(config["inputs"]["candidate_children"]["path"]),
        list(candidate_child_rows),
    )
    config_raw = _canonical_bytes(config)
    config_path.write_bytes(config_raw)
    digest = _sha256(config_raw)
    projection = SimpleNamespace(
        parents=tuple(
            SimpleNamespace(to_json=lambda row=row: copy.deepcopy(row))
            for row in candidate_parent_rows
        ),
        children=tuple(
            SimpleNamespace(to_json=lambda row=row: copy.deepcopy(row))
            for row in candidate_child_rows
        ),
    )
    compose_calls: list[tuple[object, object, object]] = []
    fidelity_calls: list[dict[str, object]] = []

    def compose(data: object, page: object, topic: object):
        compose_calls.append((data, page, topic))
        return projection

    def build(**kwargs: object):
        fidelity_calls.append(kwargs)
        return _fidelity_result()

    semantic_inputs = SimpleNamespace(
        pages=lambda: (),
        revisions=lambda: (),
        iter_data_page_mappings=lambda: (),
    )
    monkeypatch.setattr(
        module.CrawlerSemanticInputs,
        "from_root",
        lambda _root: semantic_inputs,
    )
    monkeypatch.setattr(module, "build_page_revision_join", lambda *_args: object())
    monkeypatch.setattr(
        module, "project_crawler_semantics", lambda *_args: evidence.data_projection
    )
    monkeypatch.setattr(
        module, "project_page_semantics", lambda *_args: evidence.page_projection
    )
    monkeypatch.setattr(
        module, "project_topic_semantics", lambda *_args: evidence.topic_projection
    )
    monkeypatch.setattr(module, "compose_corpus_projection", compose)
    loaded_evidence = module.load_validated_evidence(config)
    assert loaded_evidence.projection is projection
    assert loaded_evidence.candidate_parent_rows == candidate_parent_rows
    assert loaded_evidence.candidate_child_rows == candidate_child_rows
    assert compose_calls == [
        (evidence.data_projection, evidence.page_projection, evidence.topic_projection)
    ]

    monkeypatch.setattr(
        module, "load_validated_evidence", lambda _config: loaded_evidence
    )
    monkeypatch.setattr(module, "build_fidelity_ledger", build)
    monkeypatch.setattr(module, "read_git_identity", lambda _root: (HEAD, TREE))

    _invoke(module, config_path, digest, output_root)

    assert len(compose_calls) == 1
    assert len(fidelity_calls) == 1
    call = fidelity_calls[0]
    assert call["projection"] is projection
    assert call["active_parent_rows"] == loaded_evidence.active_parent_rows
    assert call["active_child_rows"] == loaded_evidence.active_child_rows
    assert call["legacy_media"] is loaded_evidence.legacy_media
    summary = json.loads((output_root / OUTPUT_NAMES[2]).read_bytes())
    assert summary["fidelity_returned_normally"] is True
    assert summary["story_blocker_prefix_counts"] == {
        "blocked_ambiguous_child": 1,
        "blocked_ambiguous_parent": 1,
        "unexplained_child_missing": 1,
        "unexplained_parent_missing": 1,
    }
    assert summary["non_story_media_blocker_counts"] == {
        "ambiguous_binding": 2,
        "conflicting_binding": 1,
        "missing_local_bytes": 3,
        "missing_resource_metadata": 0,
    }
    assert summary["other_blocker_prefix_counts"] == {
        "blocked_ambiguous_child": 1,
        "unexplained_binding_loss": 6,
        "unexplained_parent_child_loss": 1,
    }
    story_evidence = summary["story_partition_evidence"]
    assert story_evidence["source_identity_sha256"] == _hashed(
        "Data:Story/9.json\0" + "a" * 64
    )
    assert story_evidence["legacy_child_identity_sha256"] == _hashed(
        "story:9/profile:0000"
    )
    assert story_evidence["candidate_child_identity_sha256"] == [
        _hashed("story:9/story:step-0000"),
        _hashed("story:9/story:step-0001"),
    ]
    non_story_evidence = summary["non_story_partition_evidence"]
    assert non_story_evidence == {
        "record_count": 1,
        "partition_sha256": (
            "776f6df8e213b5427da2957dc7a1320c7e999b0cf043238c144de50a6fae3f90"
        ),
        "record_kind_counts": {"child": 1},
        "classification_counts": {"blocked_ambiguous": 1},
        "reason_code_counts": {"candidate_identity_ambiguous": 1},
    }
    assert "story" not in json.dumps(summary["non_story_media_blocker_counts"])


def test_diagnostic_writes_only_three_canonical_create_new_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_diagnostic()
    empty_config_path, empty_digest, empty_output, empty_config = _run_config(
        tmp_path / "preexisting-empty"
    )
    empty_output.mkdir(parents=True)
    reached = {"git": 0, "projection": 0, "fidelity": 0}

    def reached_git(_root: Path) -> tuple[str, str]:
        reached["git"] += 1
        return HEAD, TREE

    def reached_projection(_config: object) -> SimpleNamespace:
        reached["projection"] += 1
        return _test_evidence_fixture()

    def reached_fidelity(**_kwargs: object) -> SimpleNamespace:
        reached["fidelity"] += 1
        return _fidelity_result()

    monkeypatch.setattr(module, "read_git_identity", reached_git)
    monkeypatch.setattr(module, "load_validated_evidence", reached_projection)
    monkeypatch.setattr(module, "build_fidelity_ledger", reached_fidelity)
    original_load_run_config = module.load_run_config
    monkeypatch.setattr(
        module,
        "load_run_config",
        lambda *_args, **_kwargs: empty_config,
    )
    with pytest.raises(FileExistsError, match="create-new"):
        _invoke(module, empty_config_path, empty_digest, empty_output)
    assert reached == {"git": 0, "projection": 0, "fidelity": 0}
    assert tuple(empty_output.iterdir()) == ()
    monkeypatch.setattr(module, "load_run_config", original_load_run_config)

    config_path, digest, output_root, config = _run_config(tmp_path)
    monkeypatch.setattr(module, "read_git_identity", lambda _root: (HEAD, TREE))
    monkeypatch.setattr(module, "load_validated_evidence", lambda _config: _test_evidence_fixture())
    monkeypatch.setattr(module, "build_fidelity_ledger", lambda **_kwargs: _fidelity_result())

    _invoke(module, config_path, digest, output_root)

    assert tuple(sorted(path.name for path in output_root.iterdir())) == OUTPUT_NAMES
    documents: dict[str, dict[str, object]] = {}
    hashes: dict[str, str] = {}
    for name in OUTPUT_NAMES:
        raw = (output_root / name).read_bytes()
        assert raw == _canonical_bytes(json.loads(raw))
        documents[name] = json.loads(raw)
        hashes[name] = _sha256(raw)
        assert documents[name]["schema_version"] == OUTPUT_SCHEMAS[name]

    manifest = documents[OUTPUT_NAMES[0]]
    receipt = documents[OUTPUT_NAMES[1]]
    summary = documents[OUTPUT_NAMES[2]]
    assert manifest["run_id"] == receipt["run_id"] == summary["run_id"] == RUN_ID
    assert manifest["output_sha256"] == {OUTPUT_NAMES[2]: hashes[OUTPUT_NAMES[2]]}
    assert receipt["output_sha256"] == {
        OUTPUT_NAMES[0]: hashes[OUTPUT_NAMES[0]],
        OUTPUT_NAMES[2]: hashes[OUTPUT_NAMES[2]],
    }
    assert manifest["run_config"] == {
        "path": config_path.name,
        "sha256": digest,
        "size_bytes": config_path.stat().st_size,
    }
    assert manifest["diagnostic"] == {
        "path": SCRIPT_RELATIVE_PATH,
        "sha256": SCRIPT_SHA256,
    }
    assert manifest["git_identity"] == {"head": HEAD, "tree": TREE}
    repository_root = Path(config["repository_root"])
    expected_checkpoints = {
        "task7_c8a_commit": C8A_COMMIT,
        "c8b_commit": C8B_COMMIT,
        "c8b_d_acceptance": {
            "identity": "frozen/d-acceptance-c8b.json",
            "sha256": C8B_RECEIPT_SHA256,
            "size": 3622,
        },
        "c8c_commit": C8C_COMMIT,
        "c8c_d_acceptance": {
            "identity": "frozen/d-accept-c8c-final.json",
            "sha256": C8C_RECEIPT_SHA256,
            "size": 3705,
        },
    }
    expected_inputs = {
        label: {
            "identity": Path(identity["path"]).relative_to(
                repository_root
            ).as_posix(),
            "sha256": identity["sha256"],
            "size": identity["size_bytes"],
            **(
                {"row_count": identity["row_count"]}
                if "row_count" in identity
                else {}
            ),
        }
        for label, identity in config["inputs"].items()
    }
    assert manifest["accepted_checkpoints"] == expected_checkpoints
    assert manifest["inputs"] == expected_inputs
    assert manifest["c8c_evidence_chain"] == config["c8c_evidence_chain"]
    assert receipt["output_confinement"] == {
        "create_new": True,
        "output_root": RUN_ID,
        "unexpected_output_count": 0,
        "writes_outside_exact_outputs": 0,
    }
    assert receipt["protected_state"] == {
        "identity_count_pre": 32,
        "identity_count_post": 32,
        "drift_count": 0,
    }
    assert receipt["activity_counters"] == ACTIVITY_COUNTERS
    encoded_identity_chain = json.dumps(manifest, ensure_ascii=False).lower()
    assert str(tmp_path).lower().replace("\\", "/") not in encoded_identity_chain
    for secret in ("password", "credential", "token=", "api_key"):
        assert secret not in encoded_identity_chain

    before = {path.name: path.read_bytes() for path in output_root.iterdir()}
    with pytest.raises(FileExistsError):
        _invoke(module, config_path, digest, output_root)
    assert {path.name: path.read_bytes() for path in output_root.iterdir()} == before

    for drift_kind in ("content", "size", "membership", "timestamp"):
        drift_config_path, drift_digest, drift_output, drift_config = _run_config(
            tmp_path / f"protected-{drift_kind}"
        )
        protected_path = Path(
            drift_config["inputs"]["protected_identity_manifest"]["path"]
        )
        protected = json.loads(protected_path.read_bytes())
        target = Path(protected["records"][0]["path"])

        def drift_then_build(
            **_kwargs: object,
        ) -> SimpleNamespace:
            if drift_kind == "content":
                target.write_bytes(b"X" * target.stat().st_size)
            elif drift_kind == "size":
                target.write_bytes(target.read_bytes() + b"X")
            elif drift_kind == "membership":
                target.unlink()
            else:
                stat = target.stat()
                os.utime(
                    target,
                    ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000),
                )
            return _fidelity_result()

        monkeypatch.setattr(module, "read_git_identity", lambda _root: (HEAD, TREE))
        monkeypatch.setattr(
            module,
            "load_validated_evidence",
            lambda _config: _test_evidence_fixture(),
        )
        monkeypatch.setattr(module, "build_fidelity_ledger", drift_then_build)
        with pytest.raises(ValueError, match="protected.*drift"):
            _invoke(module, drift_config_path, drift_digest, drift_output)
        _assert_no_output(drift_output)


def test_diagnostic_blocks_network_external_writers_and_media_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_diagnostic()
    platform.system()
    config_path, digest, output_root, config = _run_config(tmp_path)
    forbidden: list[str] = []
    subprocess_counts = {"total": 0, "allowed": 0, "forbidden": 0}
    real_builtin_open = builtins.open
    real_io_open = io.open

    def reject(name: str) -> Callable[..., Any]:
        def blocked(*_args: object, **_kwargs: object) -> Any:
            forbidden.append(name)
            raise AssertionError(f"forbidden operation: {name}")

        return blocked

    monkeypatch.setattr(socket, "create_connection", reject("network"))
    monkeypatch.setattr(socket.socket, "connect", reject("network"))
    monkeypatch.setattr(socket.socket, "connect_ex", reject("network"))

    def guarded_run(argv: object, **kwargs: object):
        subprocess_counts["total"] += 1
        expected_kwargs = {
            "cwd": Path(config["repository_root"]),
            "check": True,
            "capture_output": True,
            "text": True,
            "shell": False,
        }
        if tuple(argv) != ("git", "rev-parse", "HEAD", "HEAD^{tree}") or kwargs != expected_kwargs:
            subprocess_counts["forbidden"] += 1
            raise AssertionError("arbitrary subprocess rejected")
        subprocess_counts["allowed"] += 1
        return subprocess.CompletedProcess(argv, 0, f"{HEAD}\n{TREE}\n", "")

    monkeypatch.setattr(subprocess, "run", guarded_run)

    exact_outputs = {path.resolve() for path in (output_root / name for name in OUTPUT_NAMES)}
    repository_root = Path(config["repository_root"]).resolve()
    allowed_reads = {
        config_path.resolve(),
        (repository_root / SCRIPT_RELATIVE_PATH).resolve(),
        *(
            Path(identity["path"]).resolve()
            for identity in config["inputs"].values()
        ),
        *(
            Path(config["accepted_checkpoints"][name]["path"]).resolve()
            for name in ("c8b_d_acceptance", "c8c_d_acceptance")
        ),
        *exact_outputs,
    }
    product_manifest_path = Path(
        config["inputs"]["c8c_product_manifest"]["path"]
    ).resolve()
    allowed_reads.add(product_manifest_path.with_name("diagnostic.product-parity.py"))
    allowed_reads.add(
        Path(config["inputs"]["c8b_taxonomy"]["path"])
        .with_name("manifest.c8b3.v1.json")
        .resolve()
    )
    protected_state = json.loads(
        Path(config["inputs"]["protected_identity_manifest"]["path"]).read_bytes()
    )
    allowed_reads.update(
        Path(record["path"]).resolve() for record in protected_state["records"]
    )
    code_roots = tuple(
        path.resolve()
        for path in (
            Path(__file__).resolve().parents[1] / "src",
            Path(__file__).resolve().parents[1] / "scripts",
        )
    )
    local_media_path = (
        Path(config["inputs"]["resource_metadata"]["path"]).parent
        / "media"
        / "arbitrary-resource.dat"
    ).resolve()
    assert local_media_path.is_file()
    assert local_media_path not in allowed_reads

    def guard_open(delegate: Callable[..., Any]) -> Callable[..., Any]:
        def guarded(file: object, mode: str = "r", *args: object, **kwargs: object):
            path = Path(file).resolve() if isinstance(file, (str, Path)) else None
            if path is not None and any(flag in mode for flag in "wax+"):
                if path not in exact_outputs:
                    return reject("write_outside_exact_outputs")(file, mode)
            if path is not None and "r" in mode:
                code_read = path.suffix in {".py", ".pyc"} and any(
                    path.is_relative_to(root) for root in code_roots
                )
                if path not in allowed_reads and not code_read:
                    return reject("local_media_byte_read")(file, mode)
            return delegate(file, mode, *args, **kwargs)

        return guarded

    monkeypatch.setattr(builtins, "open", guard_open(real_builtin_open))
    monkeypatch.setattr(io, "open", guard_open(real_io_open))

    adapter_boundaries = (
        ("src.assets.minio_store", "MinioAssetStorage", "upload_file", "minio"),
        (
            "src.huiji_rag.minio_strict",
            "StrictMinioUploader",
            "upload_sequence",
            "minio",
        ),
        ("src.huiji_rag.activation", None, "apply_activation", "activation"),
        ("src.huiji_rag.build.media_v3", None, "reconcile_media_v3_minio", "minio"),
        ("src.huijiwiki.resource_downloader", "ResourceDownloader", "run", "download"),
        ("src.huiji_rag.closure", None, "_query_database_state", "mysql"),
        ("src.huiji_rag.io", None, "_capture_milvus_observation", "milvus"),
        ("src.huiji_rag.provenance", None, "_runtime_milvus_client", "milvus"),
        (
            "src.huiji_rag.build.orchestrator",
            "HuijiCorpusBuilder",
            "build_candidate",
            "vector",
        ),
    )
    for module_name, class_name, attribute, label in adapter_boundaries:
        target_module = importlib.import_module(module_name)
        target = getattr(target_module, class_name) if class_name else target_module
        assert hasattr(target, attribute), f"missing guard boundary: {module_name}.{attribute}"
        monkeypatch.setattr(target, attribute, reject(label))

    # The exact accepted C8c manifest-schema RED is owned by the first node;
    # keep this node focused on offline/read/write confinement.
    monkeypatch.setattr(module, "_validate_c8c_chain", lambda *_args: None)
    monkeypatch.setattr(module, "load_validated_evidence", lambda _config: _test_evidence_fixture())
    monkeypatch.setattr(module, "build_fidelity_ledger", lambda **_kwargs: _fidelity_result())
    _invoke(module, config_path, digest, output_root)

    assert forbidden == []
    assert subprocess_counts == {"total": 1, "allowed": 1, "forbidden": 0}
    receipt = json.loads((output_root / OUTPUT_NAMES[1]).read_bytes())
    assert receipt["activity_counters"] == ACTIVITY_COUNTERS


def test_summary_compacts_non_story_partition_beyond_sample_limit() -> None:
    module = _load_diagnostic()
    rows = []
    for index in range(7):
        row = copy.deepcopy(_non_story_ledger_row())
        row["record_kind"] = "child" if index < 4 else "parent"
        row["active_identity"] = f"character:{index}/profile"
        row["candidate_identities"] = [f"character:{index}/profile-v2"]
        if index >= 4:
            row["classification"] = "corrected_semantics"
            row["reason_code"] = "section_semantics_changed"
        rows.append(row)
    fidelity = SimpleNamespace(passed=False, blockers=(), ledger_rows=tuple(rows))
    config = {
        "run_id": RUN_ID,
        "sample_limit_per_blocker_prefix": 2,
        "expected_protected_identity_count": 32,
        "expected_legacy_media_category_counts": {
            category: 0 for category in MEDIA_COUNTS
        },
    }

    summary = module._summary(config, fidelity)
    evidence = summary["non_story_partition_evidence"]

    assert isinstance(evidence, dict), "full non-Story rows must not be serialized"
    assert set(evidence) == {
        "record_count",
        "partition_sha256",
        "record_kind_counts",
        "classification_counts",
        "reason_code_counts",
    }
    assert evidence["record_count"] == 7
    assert evidence["record_kind_counts"] == {"child": 4, "parent": 3}
    assert evidence["classification_counts"] == {
        "blocked_ambiguous": 4,
        "corrected_semantics": 3,
    }
    assert evidence["reason_code_counts"] == {
        "candidate_identity_ambiguous": 4,
        "section_semantics_changed": 3,
    }
    assert len(evidence["partition_sha256"]) == 64
    assert all(not isinstance(value, list) for value in evidence.values())
    assert all(len(samples) <= 2 for samples in summary["structured_samples"].values())
    single_evidence = module._summary(
        config,
        SimpleNamespace(passed=False, blockers=(), ledger_rows=(rows[0],)),
    )["non_story_partition_evidence"]
    assert set(single_evidence) == set(evidence)
    assert all(not isinstance(value, list) for value in single_evidence.values())


@pytest.mark.parametrize(
    "changed_field",
    (
        "record_kind",
        "classification",
        "reason_code",
        "active_identity",
        "candidate_identities",
        "source_evidence",
    ),
)
def test_non_story_partition_digest_is_order_independent_and_field_complete(
    changed_field: str,
) -> None:
    module = _load_diagnostic()
    rows = []
    for index in range(3):
        row = copy.deepcopy(_non_story_ledger_row())
        row["active_identity"] = f"character:{index}/profile"
        row["candidate_identities"] = [f"character:{index}/profile-v2"]
        rows.append(row)
    fidelity = SimpleNamespace(ledger_rows=tuple(rows))
    reversed_fidelity = SimpleNamespace(ledger_rows=tuple(reversed(rows)))

    baseline = module._partition_summary(fidelity)[1]
    reversed_evidence = module._partition_summary(reversed_fidelity)[1]

    assert reversed_evidence == baseline
    changed_rows = copy.deepcopy(rows)
    changed = changed_rows[0]
    if changed_field == "record_kind":
        changed[changed_field] = "parent"
    elif changed_field == "classification":
        changed[changed_field] = "corrected_semantics"
    elif changed_field == "reason_code":
        changed[changed_field] = "section_semantics_changed"
    elif changed_field == "active_identity":
        changed[changed_field] = "character:changed/profile"
    elif changed_field == "candidate_identities":
        changed[changed_field] = ["character:changed/profile-v2"]
    else:
        changed[changed_field][0]["source_content_sha256"] = "e" * 64
    changed_evidence = module._partition_summary(
        SimpleNamespace(ledger_rows=tuple(changed_rows))
    )[1]

    assert changed_evidence["partition_sha256"] != baseline["partition_sha256"]


def test_diagnostic_bounds_sanitizes_and_deterministically_orders_samples(
    tmp_path: Path
) -> None:
    module = _load_diagnostic()
    for invalid_limit in (0, 6, True, 1.0):
        with pytest.raises(ValueError, match="sample limit"):
            module.bounded_structured_samples([], limit_per_prefix=invalid_limit)
    for valid_limit in range(1, 6):
        assert module.bounded_structured_samples(
            [], limit_per_prefix=valid_limit
        ) == {}
    rows = []
    for index in range(7):
        rows.append(
            {
                "blocker_prefix": "blocked_ambiguous_child",
                "record_kind": "child",
                "classification": "blocked_ambiguous",
                "reason_code": "unmatched_source_group",
                "active_identity": f"story:private:{index}/profile:0000",
                "candidate_identities": [
                    f"story:private:{index}/story:step-0000"
                ],
                "source_evidence": [
                    {
                        "source_title": f"Data:Story/private-{index}.json",
                        "source_content_sha256": "a" * 64,
                        "json_path": "$.steps",
                    }
                ],
                "raw_text": "{{secret wikitext}} password=hunter2",
                "absolute_path": f"{tmp_path}/private-{index}.json",
            }
        )
    rows.append(
        {
            "blocker_prefix": "legacy_media_conflicting_binding",
            "record_kind": "media",
            "classification": "conflicting_binding",
            "reason_code": "current_closure_conflict",
            "active_identity": "media:sha1:" + "f" * 40,
            "candidate_identities": ["binding:sha256:" + "e" * 64],
            "source_evidence": [
                {
                    "source_title": "crawler-resource:"
                    + "d" * 40
                    + ":private.png",
                    "source_content_sha256": "c" * 64,
                    "json_path": "$.resources[0]",
                }
            ],
            "raw_text": "token=secret",
            "absolute_path": "C:\\private\\raw.png",
        }
    )

    first = module.bounded_structured_samples(rows, limit_per_prefix=5)
    second = module.bounded_structured_samples(
        tuple(reversed(rows)), limit_per_prefix=5
    )

    assert first == second
    assert list(first) == sorted(first)
    assert len(first["blocked_ambiguous_child"]) == 5
    assert len(first["legacy_media_conflicting_binding"]) == 1
    for prefix, samples in first.items():
        assert samples == sorted(
            samples,
            key=lambda row: tuple(str(row[field]) for field in sorted(SAMPLE_FIELDS)),
        )
        for sample in samples:
            assert set(sample) == SAMPLE_FIELDS
            for field in (
                "active_identity_sha256",
                "candidate_identities_sha256",
            ):
                assert len(sample[field]) == 64
                int(sample[field], 16)
            assert sample["candidate_identity_count"] >= 0
            assert sample["source_evidence_count"] >= 0

    encoded = json.dumps(first, ensure_ascii=False).lower()
    for forbidden_text in (
        "story:private",
        "media:sha1",
        "binding:sha256",
        "data:story",
        "crawler-resource",
        "private.png",
        "c:\\private",
        str(tmp_path).lower(),
        "hunter2",
        "secret wikitext",
        "password",
        "token=",
        "raw_text",
        "absolute_path",
        '"active_identity":',
        '"candidate_identities":',
        '"source_evidence":',
        '"blocker_prefix":',
    ):
        assert forbidden_text not in encoded


def test_diagnostic_fails_closed_on_hash_head_tree_path_or_output_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _load_diagnostic()
    adapter_config_path, adapter_digest, adapter_output, adapter_config = _run_config(
        tmp_path / "strict-adapter"
    )

    def jsonl_rows(label: str) -> list[dict[str, object]]:
        path = Path(adapter_config["inputs"][label]["path"])
        return [json.loads(line) for line in path.read_text().splitlines()]

    taxonomy = json.loads(
        Path(adapter_config["inputs"]["c8c_taxonomy"]["path"]).read_bytes()
    )
    active_media = jsonl_rows("active_media")
    candidate_media = jsonl_rows("candidate_media_v3")
    resource_metadata = jsonl_rows("resource_metadata")
    assert len(resource_metadata) > len(
        {row["source_sha1"] for row in candidate_media}
    )
    assert all(
        candidate["title"]
        != next(
            resource["title"]
            for resource in resource_metadata
            if (
                resource["sha1"],
                resource["name"],
                resource["size"],
            )
            == (
                candidate["source_sha1"],
                candidate["filename"],
                candidate["size"],
            )
        )
        for candidate in candidate_media
    )
    reconciled = module._strict_c8c_adapter(
        taxonomy, active_media, candidate_media, resource_metadata
    )
    assert reconciled.active_occurrence_count == len(active_media)
    title_variant_candidates = copy.deepcopy(candidate_media)
    title_variant_candidates[0]["title"] = (
        "A different natural-language description remains valid"
    )
    assert module._strict_c8c_adapter(
        taxonomy,
        active_media,
        title_variant_candidates,
        resource_metadata,
    ).active_occurrence_count == len(active_media)

    trailing_newline_taxonomy = copy.deepcopy(taxonomy)
    trailing_newline_taxonomy["rows"][0][
        "legacy_row_sha256"
    ] = _sha256(_canonical_bytes(active_media[0]))
    with pytest.raises(ValueError, match="active row"):
        module._strict_c8c_adapter(
            trailing_newline_taxonomy,
            active_media,
            candidate_media,
            resource_metadata,
        )

    proven_collision_taxonomy = copy.deepcopy(taxonomy)
    proven_collision_taxonomy["coverage_checks"][
        "proven_candidate_consumption_collision_count"
    ] = 1
    proven_collision_taxonomy["duplicate_consumption_checks"][
        "proven_candidate_consumption_collision_count"
    ] = 1
    with pytest.raises(ValueError):
        module._strict_c8c_adapter(
            proven_collision_taxonomy,
            active_media,
            candidate_media,
            resource_metadata,
        )

    # Removing the sole exact triple match leaves only a valid same-SHA1
    # alternative, which must not be accepted as the candidate's resource.
    with pytest.raises(ValueError, match="resource metadata"):
        module._strict_c8c_adapter(
            taxonomy, active_media, candidate_media, resource_metadata[1:]
        )
    # Repeated SHA1 is valid, but two rows with the same concrete triple are
    # non-unique and must fail closed.
    with pytest.raises(ValueError, match="resource metadata"):
        module._strict_c8c_adapter(
            taxonomy,
            active_media,
            candidate_media,
            [*resource_metadata, copy.deepcopy(resource_metadata[0])],
        )
    for field, conflicting_value in (
        ("sha1", "0" * 40),
        ("name", "conflicting-name.png"),
        ("size", 999),
    ):
        conflicting_metadata = copy.deepcopy(resource_metadata)
        conflicting_metadata[0][field] = conflicting_value
        with pytest.raises(ValueError, match="resource metadata"):
            module._strict_c8c_adapter(
                taxonomy, active_media, candidate_media, conflicting_metadata
            )
    for field, conflicting_value in (
        ("source_sha1", "0" * 40),
        ("filename", "conflicting-name.png"),
        ("size", 999),
    ):
        conflicting_candidate_media = copy.deepcopy(candidate_media)
        conflicting_candidate_media[0][field] = conflicting_value
        with pytest.raises(ValueError, match="resource metadata"):
            module._strict_c8c_adapter(
                taxonomy,
                active_media,
                conflicting_candidate_media,
                resource_metadata,
            )

    base_config_path, base_digest, _, base_config = _run_config(tmp_path / "base")
    protected_root = Path(base_config["protected_state_root"])
    protected_manifest_path = Path(
        base_config["inputs"]["protected_identity_manifest"]["path"]
    )
    protected_manifest_raw = protected_manifest_path.read_bytes()
    protected_manifest = json.loads(protected_manifest_raw)
    assert module._validate_protected_state(
        protected_manifest_raw,
        protected_root,
        expected_count=32,
    ) == tuple(protected_manifest["records"])

    outside_record_manifest = copy.deepcopy(protected_manifest)
    outside_path = Path(base_config["repository_root"]) / SCRIPT_RELATIVE_PATH
    outside_raw = outside_path.read_bytes()
    outside_stat = outside_path.stat()
    outside_record_manifest["records"][0] = {
        **outside_record_manifest["records"][0],
        "path": outside_path.as_posix(),
        "sha256": _sha256(outside_raw),
        "size": len(outside_raw),
        "mtime_ns": outside_stat.st_mtime_ns,
    }
    with pytest.raises(ValueError):
        module._validate_protected_state(
            _canonical_bytes(outside_record_manifest),
            protected_root,
            expected_count=32,
        )

    def create_required_symlink(
        link: Path, target: Path, *, target_is_directory: bool = False
    ) -> bool:
        try:
            link.symlink_to(target, target_is_directory=target_is_directory)
        except NotImplementedError:
            return False
        except OSError as error:
            unavailable_errnos = {
                errno.EACCES,
                errno.EPERM,
                errno.ENOSYS,
                getattr(errno, "EOPNOTSUPP", errno.ENOSYS),
            }
            if (
                error.errno in unavailable_errnos
                or getattr(error, "winerror", None) == 1314
            ):
                return False
            raise
        return True

    protected_root_link = tmp_path / "protected-state-root-link"
    protected_root_symlink_available = create_required_symlink(
        protected_root_link,
        protected_root,
        target_is_directory=True,
    )
    if protected_root_symlink_available:
        with pytest.raises(ValueError):
            module._validate_protected_state(
                protected_manifest_raw,
                protected_root_link,
                expected_count=32,
            )

    protected_record_link = protected_root / "protected-record-link.txt"
    protected_record_symlink_available = create_required_symlink(
        protected_record_link,
        Path(protected_manifest["records"][0]["path"]),
    )
    if protected_record_symlink_available:
        symlink_record_manifest = copy.deepcopy(protected_manifest)
        symlink_record_manifest["records"][0]["path"] = protected_record_link.as_posix()
        with pytest.raises(ValueError):
            module._validate_protected_state(
                _canonical_bytes(symlink_record_manifest),
                protected_root,
                expected_count=32,
            )

    for index, malformed_bm25 in enumerate(
        ([], {}, {"records": {}}, {"records": [], "unexpected": True})
    ):
        case_root = tmp_path / f"bm25-malformed-{index}"
        case_config_path, _, case_output, case_config = _run_config(case_root)
        bm25_path = Path(case_config["inputs"]["active_child_bm25"]["path"])
        bm25_raw = _canonical_bytes(malformed_bm25)
        bm25_path.write_bytes(bm25_raw)
        case_config["inputs"]["active_child_bm25"] = _identity(
            bm25_path, bm25_raw
        )
        case_raw = _canonical_bytes(case_config)
        case_config_path.write_bytes(case_raw)
        with pytest.raises(ValueError, match="BM25"):
            module.load_run_config(
                case_config_path,
                expected_run_config_sha256=_sha256(case_raw),
                output_root=case_output,
            )

    calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def git_run(argv: object, **kwargs: object):
        calls.append((tuple(argv), kwargs))
        return subprocess.CompletedProcess(argv, 0, f"{HEAD}\n{TREE}\n", "")

    with monkeypatch.context() as git_patch:
        git_patch.setattr(module.subprocess, "run", git_run)
        assert module.read_git_identity(Path(base_config["repository_root"])) == (
            HEAD,
            TREE,
        )
    assert calls == [
        (
            ("git", "rev-parse", "HEAD", "HEAD^{tree}"),
            {
                "cwd": Path(base_config["repository_root"]),
                "check": True,
                "capture_output": True,
                "text": True,
                "shell": False,
            },
        )
    ]

    def run_case(
        name: str,
        mutate: Callable[[dict[str, Any], Path], None],
        *,
        raw_override: Callable[[bytes], bytes] | None = None,
        expected_digest_override: str | None = None,
        prepare: Callable[[dict[str, Any], Path], None] | None = None,
    ) -> None:
        case_root = tmp_path / name
        config_path, digest, output_root, config = _run_config(case_root)
        case = copy.deepcopy(config)
        mutate(case, case_root)
        if prepare is not None:
            prepare(case, case_root)
        raw = _canonical_bytes(case)
        if raw_override is not None:
            raw = raw_override(raw)
        config_path.write_bytes(raw)
        actual_digest = _sha256(raw)
        expected_digest = expected_digest_override or actual_digest
        before = (
            {path.name: path.read_bytes() for path in Path(case["output_root"]).iterdir()}
            if Path(case["output_root"]).is_dir()
            else {}
        )
        with pytest.raises(
            (FileExistsError, OSError, RuntimeError, subprocess.SubprocessError, ValueError)
        ):
            module.run_diagnostic(
                config_path,
                expected_run_config_sha256=expected_digest,
                output_root=Path(case["output_root"]),
            )
        after = (
            {path.name: path.read_bytes() for path in Path(case["output_root"]).iterdir()}
            if Path(case["output_root"]).is_dir()
            else {}
        )
        assert after == before
        assert not any(case_root.rglob("*.partial"))
        assert not any(case_root.rglob("*.tmp"))

    cases: list[tuple[str, Callable[[dict[str, Any], Path], None]]] = [
        ("wrong-head", lambda c, _r: c.__setitem__("expected_git_head", "0" * 40)),
        ("wrong-tree", lambda c, _r: c.__setitem__("expected_git_tree", "0" * 40)),
        (
            "wrong-input-hash",
            lambda c, _r: c["inputs"]["active_parents"].__setitem__("sha256", "0" * 64),
        ),
        (
            "wrong-input-size",
            lambda c, _r: c["inputs"]["active_parents"].__setitem__("size_bytes", 999),
        ),
        (
            "wrong-row-count",
            lambda c, _r: c["inputs"]["active_parents"].__setitem__("row_count", 999),
        ),
        (
            "path-escape",
            lambda c, r: c["inputs"]["active_parents"].__setitem__(
                "path", (r.parent / "outside.jsonl").as_posix()
            ),
        ),
        (
            "script-drift",
            lambda c, _r: c["diagnostic"].__setitem__("sha256", "0" * 64),
        ),
        (
            "receipt-drift",
            lambda c, _r: c["accepted_checkpoints"]["c8c_d_acceptance"].__setitem__(
                "sha256", "0" * 64
            ),
        ),
        (
            "checkpoint-drift",
            lambda c, _r: c["accepted_checkpoints"].__setitem__("c8b_commit", "0" * 40),
        ),
        (
            "evidence-chain-drift",
            lambda c, _r: c["c8c_evidence_chain"].__setitem__(
                "summary_sha256", "0" * 64
            ),
        ),
        (
            "run-id-output-mismatch",
            lambda c, r: c.__setitem__("output_root", (r / "wrong-run-id").as_posix()),
        ),
        ("unknown-top-field", lambda c, _r: c.__setitem__("surprise", True)),
        ("missing-top-field", lambda c, _r: c.pop("accepted_checkpoints")),
        (
            "unknown-input-field",
            lambda c, _r: c["inputs"]["active_parents"].__setitem__("surprise", True),
        ),
        (
            "missing-input-field",
            lambda c, _r: c["inputs"]["active_parents"].pop("sha256"),
        ),
        (
            "product-schema-drift",
            lambda c, _r: c["inputs"]["c8c_product_manifest"].__setitem__(
                "sha256", "0" * 64
            ),
        ),
    ]
    for name, mutation in cases:
        run_case(name, mutation)

    run_case(
        "wrong-run-config-digest",
        lambda _c, _r: None,
        expected_digest_override="0" * 64,
    )
    run_case(
        "duplicate-json-key",
        lambda _c, _r: None,
        raw_override=lambda raw: raw.replace(
            b'{"accepted_checkpoints":',
            b'{"schema_version":"duplicate","accepted_checkpoints":',
            1,
        ),
    )

    def make_symlink(case: dict[str, Any], root: Path) -> None:
        target = Path(case["inputs"]["active_parents"]["path"])
        replacement = root / "symlink-parents.jsonl"
        replacement.symlink_to(target)
        case["inputs"]["active_parents"] = {
            **case["inputs"]["active_parents"],
            "path": replacement.as_posix(),
        }

    try:
        run_case(
            "symlink-input",
            lambda _c, _r: None,
            prepare=make_symlink,
        )
    except OSError as error:
        if getattr(error, "winerror", None) != 1314:
            raise

    def colliding_output(case: dict[str, Any], _root: Path) -> None:
        output = Path(case["output_root"])
        output.mkdir(parents=True)
        (output / OUTPUT_NAMES[2]).write_bytes(b"preexisting\n")

    run_case(
        "output-collision",
        lambda _c, _r: None,
        prepare=colliding_output,
    )

    second_root = tmp_path / "second-subprocess"
    second_config_path, second_digest, second_output, _ = _run_config(second_root)
    second_subprocess_calls: list[tuple[tuple[str, ...], dict[str, object]]] = []

    def second_subprocess(argv: object, **kwargs: object):
        second_subprocess_calls.append((tuple(argv), kwargs))
        if len(second_subprocess_calls) == 1:
            assert tuple(argv) == ("git", "rev-parse", "HEAD", "HEAD^{tree}")
            return subprocess.CompletedProcess(argv, 0, f"{HEAD}\n{TREE}\n", "")
        raise subprocess.SubprocessError("subsequent subprocess rejected")

    original_load_validated_evidence = module.load_validated_evidence

    def inject_subsequent_subprocess(config: dict[str, object]):
        module.subprocess.run(
            ("python", "unexpected.py"),
            cwd=Path(config["repository_root"]),
            check=True,
            capture_output=True,
            text=True,
            shell=False,
        )
        return original_load_validated_evidence(config)

    monkeypatch.setattr(module.subprocess, "run", second_subprocess)
    monkeypatch.setattr(module, "_validate_c8c_chain", lambda *_args: None)
    monkeypatch.setattr(
        module, "load_validated_evidence", inject_subsequent_subprocess
    )
    with pytest.raises(subprocess.SubprocessError, match="subsequent subprocess"):
        module.run_diagnostic(
            second_config_path,
            expected_run_config_sha256=second_digest,
            output_root=second_output,
        )
    assert not second_output.exists()
    assert [call[0] for call in second_subprocess_calls] == [
        ("git", "rev-parse", "HEAD", "HEAD^{tree}"),
        ("python", "unexpected.py"),
    ]
    assert _sha256(base_config_path.read_bytes()) == base_digest
