"""Read-only HTTP audit for media already indexed by a pinned Wiki snapshot."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.huiji_wiki.snapshot import WikiArtifactSnapshot
from src.huiji_wiki.snapshot import snapshot_is_stale


AuditStatus = Literal["verified", "missing", "repair-requested", "conflict", "blocked-by-evb", "stale-activation", "unverified-content-sha256"]


@dataclass(frozen=True)
class WikiMediaAuditResult:
    status: AuditStatus
    media_id: str
    url: str
    http_status: int | None
    mime: str


def audit_media(snapshot: WikiArtifactSnapshot, media_rows: Iterable[Mapping[str, object]], output: Path, *, opener=urlopen) -> dict[str, object]:
    rows = list(media_rows)
    preflight = _preflight_status(snapshot)
    if preflight:
        results = [asdict(WikiMediaAuditResult(preflight, str(row.get("media_id") or row.get("asset_id") or ""), "", None, str(row.get("mime") or ""))) for row in rows]
        report: dict[str, object] = {"schemaVersion": "wiki.media-audit/v1", "sourceMode": snapshot.source_mode, "buildVersion": snapshot.build_version, "snapshotSha256": snapshot.snapshot_sha256, "results": results}
        _write_new_json(Path(output), report)
        return report
    results: list[dict[str, Any]] = []
    for row in rows:
        media_id = str(row.get("media_id") or row.get("asset_id") or "")
        url = str(row.get("url") or "")
        mime = str(row.get("mime") or "")
        status: AuditStatus = "missing"
        http_status: int | None = None
        if url.startswith(("http://", "https://")):
            try:
                request = Request(url, headers={"User-Agent": "1999Search-WikiAudit/1.0"}, method="GET")
                with opener(request, timeout=20) as response:
                    http_status = int(getattr(response, "status", 200))
                    body = response.read()
                    response_mime = str(getattr(response, "headers", {}).get("Content-Type", "")).split(";", 1)[0]
                    expected_size = int(row.get("size") or 0)
                    sha1 = str(row.get("sha1") or "")
                    content_sha256 = str(row.get("content_sha256") or "")
                    mismatch = bool(expected_size and expected_size != len(body)) or bool(sha1 and hashlib.sha1(body).hexdigest() != sha1) or bool(content_sha256 and hashlib.sha256(body).hexdigest() != content_sha256)
                    if http_status != 200:
                        status = "missing"
                    elif mismatch or (mime and response_mime and mime != response_mime):
                        status = "conflict"
                    elif not content_sha256 and str(row.get("asset_type") or "") != "voice":
                        status = "unverified-content-sha256"
                    else:
                        status = "verified"
            except HTTPError as exc:
                http_status = exc.code
            except (URLError, OSError, ValueError):
                pass
        results.append(asdict(WikiMediaAuditResult(status, media_id, url if url.startswith(("http://", "https://")) else "", http_status, mime)))
    report: dict[str, object] = {"schemaVersion": "wiki.media-audit/v1", "sourceMode": snapshot.source_mode, "buildVersion": snapshot.build_version, "snapshotSha256": snapshot.snapshot_sha256, "results": results}
    _write_new_json(Path(output), report)
    return report


def write_repair_request(snapshot: WikiArtifactSnapshot, missing_rows: Sequence[Mapping[str, object]], output: Path) -> Path:
    preflight = _preflight_status(snapshot)
    if preflight:
        raise RuntimeError(f"media repair blocked: {preflight}")
    items = [{"mediaId": str(row.get("media_id") or row.get("asset_id") or ""), "objectKey": str(row.get("object_key") or ""), "reason": "missing-or-conflict"} for row in missing_rows]
    payload = {"schemaVersion": "wiki.media-repair-request/v1", "sourceMode": snapshot.source_mode, "buildVersion": snapshot.build_version, "snapshotSha256": snapshot.snapshot_sha256, "manifestSha256": snapshot.manifest_sha256, "items": items, "provenance": "media_assets.jsonl"}
    path = Path(output)
    _write_new_json(path, payload)
    return path


def audit_media_manifest(snapshot: WikiArtifactSnapshot, media_rows: Iterable[Mapping[str, object]], output: Path) -> dict[str, object]:
    rows = list(media_rows)
    seen_ids: dict[str, str] = {}
    results: list[dict[str, str]] = []
    for row in rows:
        media_id = str(row.get("media_id") or row.get("asset_id") or "")
        object_key = str(row.get("object_key") or "")
        url = str(row.get("url") or "")
        if not media_id or not object_key or not url.startswith(("http://", "https://")):
            status = "missing-index-fields"
        elif media_id in seen_ids and seen_ids[media_id] != object_key:
            status = "conflicting-media-id"
        else:
            status = "mapping-complete"
        if media_id:
            seen_ids.setdefault(media_id, object_key)
        results.append({"mediaId": media_id, "status": status})
    report: dict[str, object] = {
        "schemaVersion": "wiki.media-manifest-audit/v1",
        "sourceMode": snapshot.source_mode,
        "buildVersion": snapshot.build_version,
        "snapshotSha256": snapshot.snapshot_sha256,
        "rowCount": len(rows),
        "completeCount": sum(item["status"] == "mapping-complete" for item in results),
        "results": results,
    }
    _write_new_json(Path(output), report)
    return report


def _write_new_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")


def _preflight_status(snapshot: WikiArtifactSnapshot) -> AuditStatus | None:
    processed_root = snapshot.parent_blocks.parent.parent
    if snapshot_is_stale(snapshot, processed_root, snapshot.build_version):
        return "stale-activation"
    transactions = processed_root / "activation" / "transactions"
    if transactions.is_dir():
        terminal = {"committed", "rolled_back", "aborted", "conflict"}
        for journal in transactions.rglob("journal.v1.json"):
            try:
                state = json.loads(journal.read_text(encoding="utf-8")).get("state")
            except (OSError, json.JSONDecodeError):
                return "blocked-by-evb"
            if state not in terminal:
                return "blocked-by-evb"
    return None
