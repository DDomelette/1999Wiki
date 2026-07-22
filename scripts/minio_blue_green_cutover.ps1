param(
    [string]$Project = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$Evidence = (Join-Path $Project "data\processed\huiji\evidence\minio-migration-20260712")
)

$ErrorActionPreference = "Stop"
$Compose = Join-Path $Project "infra\milvus\docker-compose.yml"
$Override = Join-Path $Project "infra\milvus\docker-compose.minio-2025.yml"
$EvidenceCli = Join-Path $Project "scripts\minio_blue_green_evidence.py"
$Rollback = Join-Path $Project "scripts\minio_blue_green_rollback.ps1"
$FailedGate = "task5_initialization"

function Assert-LastExitCode([string]$Message) {
    if ($LASTEXITCODE -ne 0) { throw $Message }
}

function Wait-HttpHealthy([string]$Url, [int]$Attempts) {
    for ($i = 0; $i -lt $Attempts; $i++) {
        curl.exe --noproxy "*" --fail --silent --show-error $Url | Out-Null
        if ($LASTEXITCODE -eq 0) { return }
        Start-Sleep -Seconds 2
    }
    throw "Health check timed out: $Url"
}

Set-Location $Project
try {
    $FailedGate = "minio_recreate"
    docker compose -f $Compose -f $Override up -d --force-recreate minio
    Assert-LastExitCode "New MinIO failed to start"

    $FailedGate = "minio_health"
    Wait-HttpHealthy "http://127.0.0.1:9002/minio/health/live" 30
    $Running = docker inspect milvus-main-minio | ConvertFrom-Json
    if ($Running[0].Config.Image -ne "minio/minio:RELEASE.2025-09-07T16-13-09Z") { throw "Cutover image mismatch" }
    $RunningEnv = @{}
    foreach ($entry in $Running[0].Config.Env) {
        $parts = $entry -split "=", 2
        if ($parts.Count -eq 2) { $RunningEnv[$parts[0]] = $parts[1] }
    }
    $env:EVB_MIGRATION_ACCESS_KEY = $RunningEnv["MINIO_ROOT_USER"]
    $env:EVB_MIGRATION_SECRET_KEY = $RunningEnv["MINIO_ROOT_PASSWORD"]

    $FailedGate = "reverse1999_inventory"
    python $EvidenceCli object-inventory --endpoint 127.0.0.1:9002 --bucket reverse1999-assets --prefix reverse1999 --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "cutover-target-reverse1999-before-probe.v1.json")
    Assert-LastExitCode "Cutover reverse1999 inventory failed"
    python $EvidenceCli compare-objects --expected (Join-Path $Evidence "cutover-source-reverse1999.v1.json") --actual (Join-Path $Evidence "cutover-target-reverse1999-before-probe.v1.json") --output (Join-Path $Evidence "cutover-reverse1999-comparison.v1.json")
    Assert-LastExitCode "Cutover reverse1999 drift"

    $FailedGate = "a_bucket_inventory"
    python $EvidenceCli object-inventory --endpoint 127.0.0.1:9002 --bucket a-bucket --prefix "" --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "cutover-target-a-bucket.v1.json")
    Assert-LastExitCode "Cutover a-bucket inventory failed"
    python $EvidenceCli compare-objects --expected (Join-Path $Evidence "cutover-source-a-bucket.v1.json") --actual (Join-Path $Evidence "cutover-target-a-bucket.v1.json") --output (Join-Path $Evidence "cutover-a-bucket-comparison.v1.json")
    Assert-LastExitCode "Cutover a-bucket drift"

    $FailedGate = "capability_probe"
    python $EvidenceCli capability-probe --endpoint 127.0.0.1:9002 --bucket reverse1999-assets --prefix reverse1999/_evb_capability_probe --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "minio_capability.v1.json")
    Assert-LastExitCode "Final capability probe failed"

    $FailedGate = "milvus_start"
    docker compose -f $Compose -f $Override up -d standalone attu
    Assert-LastExitCode "Milvus or Attu failed to start"
    Wait-HttpHealthy "http://127.0.0.1:19091/healthz" 45

    $FailedGate = "milvus_compare"
    python $EvidenceCli milvus-inventory --endpoint http://127.0.0.1:19530 --database reverse1999_rag --output (Join-Path $Evidence "milvus-after.v1.json")
    Assert-LastExitCode "Post-cutover Milvus inventory failed"
    python $EvidenceCli compare-milvus --expected (Join-Path $Evidence "milvus-before.v1.json") --actual (Join-Path $Evidence "milvus-after.v1.json") --output (Join-Path $Evidence "milvus-comparison.v1.json")
    Assert-LastExitCode "Milvus post-cutover drift"

    $FailedGate = "media_samples"
    python $EvidenceCli media-samples --inventory (Join-Path $Evidence "cutover-target-reverse1999-before-probe.v1.json") --base-url http://127.0.0.1:9002/reverse1999-assets --asset-type voice --asset-type image --asset-type portrait --asset-type skill --output (Join-Path $Evidence "media-samples-after.v1.json")
    Assert-LastExitCode "Post-cutover media sample verification failed"

    $FailedGate = "cutover_receipt"
    python $EvidenceCli receipt --schema evb.minio-cutover-validation/v1 --status cutover_accepted --input "reverse1999_comparison=$(Join-Path $Evidence 'cutover-reverse1999-comparison.v1.json')" --input "a_bucket_comparison=$(Join-Path $Evidence 'cutover-a-bucket-comparison.v1.json')" --input "capability=$(Join-Path $Evidence 'minio_capability.v1.json')" --input "milvus_comparison=$(Join-Path $Evidence 'milvus-comparison.v1.json')" --input "media_samples=$(Join-Path $Evidence 'media-samples-after.v1.json')" --field target_image=minio/minio:RELEASE.2025-09-07T16-13-09Z --field host_ports=9002:9000,9003:9001 --output (Join-Path $Evidence "cutover-validation.v1.json")
    Assert-LastExitCode "Cutover receipt failed"
} catch {
    $CutoverFailure = $_
    & $Rollback -Project $Project -Evidence $Evidence -FailedGate $FailedGate
    if ($LASTEXITCODE -ne 0) { throw "Cutover gate '$FailedGate' failed and rollback also failed: $CutoverFailure" }
    throw "Cutover gate '$FailedGate' failed; rollback completed: $CutoverFailure"
}
