from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_rollback_compose_pins_old_image_and_original_volume():
    text = (ROOT / "infra/milvus/docker-compose.minio-2023-rollback.yml").read_text()
    assert "minio/minio:RELEASE.2023-03-20T20-16-18Z" in text
    assert "./volumes/minio:/minio_data" in text
    assert "minio-2025-09-07-cutover" not in text
    assert 'name: milvus-main-network' in text
    assert "external: true" in text


def test_rollback_script_is_independent_and_verifies_both_buckets():
    text = (ROOT / "scripts/minio_blue_green_rollback.ps1").read_text()
    assert "[Parameter(Mandatory = $true)][string]$FailedGate" in text
    assert "docker-compose.minio-2023-rollback.yml" in text
    assert "cutover-source-reverse1999.v1.json" in text
    assert "cutover-source-a-bucket.v1.json" in text
    assert "rollback-a-bucket-comparison.v1.json" in text
    assert "--database reverse1999_rag" in text


def test_cutover_wrapper_assigns_gates_and_automatically_invokes_rollback():
    text = (ROOT / "scripts/minio_blue_green_cutover.ps1").read_text()
    assert '$FailedGate = "task5_initialization"' in text
    assert "try {" in text
    assert "catch {" in text
    assert '$FailedGate = "minio_recreate"' in text
    assert '$FailedGate = "capability_probe"' in text
    assert '$FailedGate = "milvus_compare"' in text
    assert '$FailedGate = "cutover_receipt"' in text
    assert "minio_blue_green_rollback.ps1" in text
    assert "-FailedGate $FailedGate" in text
