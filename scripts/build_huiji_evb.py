"""Diagnostic EventName voice-binding entry point; never builds a full corpus."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import re
import sys
from typing import Sequence
from uuid import UUID

from minio.error import S3Error

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.config import get_config  # noqa: E402
from src.huiji_rag.builder import (  # noqa: E402
    EvbBuilder,
    resolve_strict_object_requests_from_build_manifest,
    strict_object_requests_from_build_manifest,
)
from src.huiji_rag.minio_strict import (  # noqa: E402
    ApplicationAuditMissing,
    CapabilityUnavailable,
    EvidenceAlreadyUsed,
    EvidenceMismatch,
    StrictMinioError,
    StrictMinioUploader,
    capture_object_inventory,
    combine_capability_evidence,
    load_and_claim_operation_plan,
    load_object_inventory,
    load_capability_evidence_from_bundle,
    load_operation_preflight_bundle,
    local_capability_evidence,
    map_s3_error,
    ordered_object_keys_sha256,
    prepare_upload_inputs,
    validate_after_inventory_delta,
    validate_capability_authority,
    validate_operation_plan_authority_path,
    write_upload_report,
)
from src.huiji_rag.models import BuildRequest  # noqa: E402


_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


def _offline_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("offline", help="validate evidence and prepare an isolated offline build")
    parser.add_argument("--build-version", required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--expected-baseline-sha256", required=True)
    parser.add_argument("--preflight-bundle", type=Path, required=True)
    parser.add_argument("--expected-preflight-bundle-sha256", required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")


def _minio_plan_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("minio-plan", help="create an immutable read-only MinIO operation plan")
    parser.add_argument("--build-manifest", type=Path, required=True)
    parser.add_argument("--expected-build-manifest-sha256", required=True)
    parser.add_argument("--preflight-bundle", type=Path, required=True)
    parser.add_argument("--expected-preflight-bundle-sha256", required=True)
    parser.add_argument("--before-inventory", type=Path, required=True)
    parser.add_argument("--expected-before-inventory-sha256", required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--expected-baseline-sha256", required=True)
    parser.add_argument("--resolution-report", type=Path)
    parser.add_argument("--output", type=Path, required=True)


def _minio_upload_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser("minio-upload", help="execute one claimed strict additive MinIO plan")
    parser.add_argument("--operation-plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--report", type=Path, required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build isolated diagnostic EventName voice-binding artifacts."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    _offline_parser(subparsers)
    _minio_plan_parser(subparsers)
    _minio_upload_parser(subparsers)
    return parser


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_path_hash(path: Path, expected: str, label: str) -> Path:
    if _SHA256_RE.fullmatch(expected) is None:
        raise ValueError(f"{label} expected SHA-256 must be lowercase hexadecimal")
    resolved = Path(path).resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"{label} does not exist")
    if _file_sha256(resolved) != expected:
        raise ValueError(f"{label} SHA-256 mismatch")
    return resolved


def _create_minio_client():
    from minio import Minio

    cfg = get_config().assets
    if not cfg.access_key or not cfg.secret_key:
        raise ValueError("MINIO_ACCESS_KEY and MINIO_SECRET_KEY are required")
    return Minio(
        cfg.endpoint,
        access_key=cfg.access_key,
        secret_key=cfg.secret_key,
        secure=cfg.secure,
    )


def _minio_authority() -> tuple[str, str, str]:
    cfg = get_config().assets
    return cfg.endpoint, cfg.bucket_name, cfg.object_prefix.rstrip("/")


def _huiji_authority_roots() -> tuple[Path, Path]:
    cfg = get_config().huiji
    return Path(cfg.raw_root).resolve(), Path(cfg.processed_root).resolve()


def _missing_plan_requests(requests, inventory):
    existing_keys = {item.object_key for item in inventory.objects}
    return tuple(request for request in requests if request.object_key not in existing_keys)


def _write_resolution_report(path: Path, payload: dict[str, object]) -> None:
    resolved = Path(path).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def _run_minio_plan(args: argparse.Namespace) -> int:
    endpoint, bucket, prefix = _minio_authority()
    raw_root, processed_root = _huiji_authority_roots()
    baseline = _validate_path_hash(args.baseline, args.expected_baseline_sha256, "baseline")
    build = _validate_path_hash(
        args.build_manifest, args.expected_build_manifest_sha256, "build manifest"
    )
    bundle = _validate_path_hash(
        args.preflight_bundle, args.expected_preflight_bundle_sha256, "preflight bundle"
    )
    inventory_path = _validate_path_hash(
        args.before_inventory, args.expected_before_inventory_sha256, "before inventory"
    )
    output = validate_operation_plan_authority_path(
        args.output,
        processed_root,
    )
    inventory = load_object_inventory(inventory_path)
    bundle_payload = json.loads(bundle.read_text(encoding="utf-8"))
    operation_preflight = None
    resolution = None
    resolution_report = None
    if (
        isinstance(bundle_payload, dict)
        and bundle_payload.get("schema_version")
        == "evb.minio-operation-preflight/v1"
    ):
        operation_preflight, sidecar_capability = load_operation_preflight_bundle(bundle)
        if operation_preflight.build_manifest_sha256 != args.expected_build_manifest_sha256:
            raise EvidenceMismatch("operation preflight build manifest differs from command")
        if operation_preflight.baseline_sha256 != args.expected_baseline_sha256:
            raise EvidenceMismatch("operation preflight baseline differs from command")
        if operation_preflight.before_inventory_sha256 != args.expected_before_inventory_sha256:
            raise EvidenceMismatch("operation preflight before inventory differs from command")
        if operation_preflight.before_inventory_object_sha256 != inventory.object_state_sha256:
            raise EvidenceMismatch("operation preflight before object state differs from inventory")
        if args.resolution_report is None:
            raise EvidenceMismatch("v3 minio-plan requires a resolution report path")
        resolution_report = Path(args.resolution_report).resolve()
        if resolution_report != output.with_name("minio_plan_resolution.v1.json"):
            raise EvidenceMismatch("v3 resolution report path is not the fixed plan sibling")
        if resolution_report.exists():
            raise FileExistsError("v3 resolution report already exists")
        resolution = resolve_strict_object_requests_from_build_manifest(
            build,
            inventory,
            raw_root,
            allowed_media_authorities=operation_preflight.allowed_media_authorities,
        )
        if (
            resolution.ordered_missing_object_keys_sha256
            != operation_preflight.approved_missing_object_keys_sha256
        ):
            raise EvidenceMismatch("derived missing object-key set differs from approval")
        if resolution.missing_remote_count != operation_preflight.approved_missing_remote_count:
            raise EvidenceMismatch("derived missing object count differs from approval")
        derived_role_counts: dict[str, int] = {}
        for label, count in resolution.missing_authority_counts:
            asset_type = label.split("/", 1)[0]
            derived_role_counts[asset_type] = derived_role_counts.get(asset_type, 0) + count
        if tuple(sorted(derived_role_counts.items())) != operation_preflight.approved_missing_role_counts:
            raise EvidenceMismatch("derived missing media counts differ from approval")
        if resolution.hash_mismatch_count:
            raise EvidenceMismatch("derived reconciliation contains a hash mismatch")
        requests = resolution.missing_requests
        if not requests:
            raise EvidenceMismatch("v3 operation plan has no missing objects")
    else:
        if args.resolution_report is not None:
            raise EvidenceMismatch("legacy minio-plan does not accept a v3 resolution report")
        sidecar_capability = load_capability_evidence_from_bundle(bundle)
        requests = _missing_plan_requests(
            strict_object_requests_from_build_manifest(build, inventory, raw_root),
            inventory,
        )

    client = _create_minio_client()
    capabilities = combine_capability_evidence(
        local_capability_evidence(client), sidecar_capability
    )
    validate_capability_authority(capabilities, endpoint=endpoint, bucket=bucket, prefix=prefix)
    uploader = StrictMinioUploader(client, capabilities, source_root=raw_root)
    plan = uploader.create_operation_plan(
        baseline,
        args.expected_baseline_sha256,
        build,
        args.expected_build_manifest_sha256,
        bundle,
        args.expected_preflight_bundle_sha256,
        inventory_path,
        args.expected_before_inventory_sha256,
        requests,
        output,
    )
    if resolution is not None and operation_preflight is not None and resolution_report is not None:
        if any(item.disposition != "conditional_create" for item in plan.objects):
            raise EvidenceMismatch("v3 operation plan contains a non-create disposition")
        if ordered_object_keys_sha256([item.object_key for item in plan.objects]) != (
            operation_preflight.approved_missing_object_keys_sha256
        ):
            raise EvidenceMismatch("written operation plan object-key set differs from approval")
        _write_resolution_report(
            resolution_report,
            {
                "schema_version": "huiji.v3-minio-plan-resolution/v1",
                "build_manifest_sha256": args.expected_build_manifest_sha256,
                "baseline_sha256": args.expected_baseline_sha256,
                "preflight_bundle_sha256": args.expected_preflight_bundle_sha256,
                "before_inventory_sha256": args.expected_before_inventory_sha256,
                "before_inventory_object_sha256": inventory.object_state_sha256,
                "approved_reconciliation_sha256": operation_preflight.reconciliation_sha256,
                "approved_missing_object_keys_sha256": (
                    operation_preflight.approved_missing_object_keys_sha256
                ),
                "allowed_media_authorities": [
                    item.to_json() for item in operation_preflight.allowed_media_authorities
                ],
                "resolution": resolution.to_json(),
                "operation_plan_path": output.name,
                "operation_plan_sha256": plan.operation_plan_sha256,
                "operation_plan_object_set_sha256": plan.object_set_sha256,
                "used_by_operation_id": plan.used_by_operation_id,
                "minio_mutation_performed": False,
            },
        )
    print(plan.operation_plan_sha256)
    return 0


def _run_minio_upload(args: argparse.Namespace) -> int:
    endpoint, bucket, prefix = _minio_authority()
    raw_root, processed_root = _huiji_authority_roots()
    plan_path = Path(args.operation_plan).resolve()
    plan, requests = prepare_upload_inputs(
        plan_path,
        args.expected_plan_sha256,
        processed_root=processed_root,
        source_root=raw_root,
        endpoint=endpoint,
        bucket=bucket,
        prefix=prefix,
        report_path=args.report,
    )
    client = _create_minio_client()
    capabilities = combine_capability_evidence(
        local_capability_evidence(client), plan.capability_evidence
    )
    capabilities.require_conditional_create_and_app_audit()
    try:
        current_inventory = capture_object_inventory(client, plan.bucket, plan.prefix)
    except (S3Error, CapabilityUnavailable) as error:
        print(f"current inventory capture failed: {error}", file=sys.stderr)
        return 5
    claimed = load_and_claim_operation_plan(plan_path, args.expected_plan_sha256, current_inventory)
    operation_id = UUID(str(claimed.used_by_operation_id))
    uploader = StrictMinioUploader(client, capabilities, source_root=raw_root)
    report = uploader.upload_sequence(
        claimed,
        requests,
        operation_id,
        current_inventory=current_inventory,
    )
    try:
        after_inventory = capture_object_inventory(client, plan.bucket, plan.prefix)
    except S3Error as error:
        capture_status = map_s3_error(error)
        report = replace(
            report,
            status="blocked" if capture_status == "blocked" else "failed",
            after_inventory_sha256=None,
            after_inventory_object_sha256=None,
            after_inventory_capture_error_code=getattr(error, "code", None),
            after_inventory_capture_request_id=getattr(error, "request_id", None),
        )
    except CapabilityUnavailable:
        report = replace(
            report,
            status="blocked",
            after_inventory_sha256=None,
            after_inventory_object_sha256=None,
            after_inventory_capture_error_code="inventory_evidence_unavailable",
            after_inventory_capture_request_id=None,
        )
    else:
        report = replace(
            report,
            after_inventory_sha256=after_inventory.inventory_sha256,
            after_inventory_object_sha256=after_inventory.object_state_sha256,
        )
        try:
            validate_after_inventory_delta(current_inventory, after_inventory, report.objects)
        except ApplicationAuditMissing:
            report = replace(report, status="blocked")
        except EvidenceMismatch:
            report = replace(report, status="failed")
    write_upload_report(args.report, report)
    print(args.report)
    if report.status == "concurrency_conflict":
        return 4
    if report.status in {"blocked", "failed"}:
        return 5
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "minio-plan":
        try:
            return _run_minio_plan(args)
        except (FileNotFoundError, FileExistsError, ValueError, StrictMinioError) as error:
            parser.error(str(error))
    if args.command == "minio-upload":
        try:
            return _run_minio_upload(args)
        except EvidenceAlreadyUsed as error:
            print(str(error), file=sys.stderr)
            return 3
        except CapabilityUnavailable as error:
            print(str(error), file=sys.stderr)
            return 3
        except EvidenceMismatch as error:
            parser.error(str(error))
        except (FileNotFoundError, FileExistsError, ValueError) as error:
            parser.error(str(error))
    request = BuildRequest(
        build_version=args.build_version,
        baseline_path=args.baseline,
        expected_baseline_sha256=args.expected_baseline_sha256,
        preflight_bundle_path=args.preflight_bundle,
        expected_preflight_bundle_sha256=args.expected_preflight_bundle_sha256,
        output_root=args.output_root,
        report_root=args.report_root,
        dry_run=args.dry_run,
    )
    try:
        result = EvbBuilder().build_offline(request)
    except (FileNotFoundError, FileExistsError, ValueError) as error:
        parser.error(str(error))
    print(result.build_manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
