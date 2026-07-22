param(
    [Parameter(Mandatory = $true)][string]$FailedGate,
    [string]$Project = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$Evidence = (Join-Path $Project "data\processed\huiji\evidence\minio-migration-20260712")
)

$ErrorActionPreference = "Stop"
$RollbackCompose = Join-Path $Project "infra\milvus\docker-compose.minio-2023-rollback.yml"
$EvidenceCli = Join-Path $Project "scripts\minio_blue_green_evidence.py"

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
docker stop -t 120 attu-main
docker stop -t 120 milvus-main-standalone
$MilvusState = docker inspect milvus-main-standalone | ConvertFrom-Json
if ($MilvusState[0].State.Running -or $MilvusState[0].State.ExitCode -ne 0) { throw "Milvus did not stop cleanly during rollback" }
docker stop -t 120 milvus-main-minio
$MinioState = docker inspect milvus-main-minio | ConvertFrom-Json
if ($MinioState[0].State.Running -or $MinioState[0].State.ExitCode -ne 0) { throw "MinIO did not stop cleanly during rollback" }

docker compose -f $RollbackCompose config --quiet
Assert-LastExitCode "Rollback Compose is invalid"
docker compose -f $RollbackCompose up -d --force-recreate minio
Assert-LastExitCode "Rollback MinIO recreation failed"
Wait-HttpHealthy "http://127.0.0.1:9002/minio/health/live" 30
docker compose -f $RollbackCompose up -d --force-recreate standalone attu
Assert-LastExitCode "Rollback Milvus or Attu recreation failed"
Wait-HttpHealthy "http://127.0.0.1:19091/healthz" 45

$RollbackInspect = docker inspect milvus-main-minio | ConvertFrom-Json
if ($RollbackInspect[0].Config.Image -ne "minio/minio:RELEASE.2023-03-20T20-16-18Z") { throw "Rollback image mismatch" }
$RollbackEnv = @{}
foreach ($entry in $RollbackInspect[0].Config.Env) {
    $parts = $entry -split "=", 2
    if ($parts.Count -eq 2) { $RollbackEnv[$parts[0]] = $parts[1] }
}
$env:EVB_MIGRATION_ACCESS_KEY = $RollbackEnv["MINIO_ACCESS_KEY"]
$env:EVB_MIGRATION_SECRET_KEY = $RollbackEnv["MINIO_SECRET_KEY"]

python $EvidenceCli object-inventory --endpoint 127.0.0.1:9002 --bucket reverse1999-assets --prefix reverse1999 --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "rollback-minio-inventory.v1.json")
Assert-LastExitCode "Rollback reverse1999 inventory failed"
python $EvidenceCli compare-objects --expected (Join-Path $Evidence "cutover-source-reverse1999.v1.json") --actual (Join-Path $Evidence "rollback-minio-inventory.v1.json") --output (Join-Path $Evidence "rollback-minio-comparison.v1.json")
Assert-LastExitCode "Rollback reverse1999 inventory differs"
python $EvidenceCli object-inventory --endpoint 127.0.0.1:9002 --bucket a-bucket --prefix "" --access-key-env EVB_MIGRATION_ACCESS_KEY --secret-key-env EVB_MIGRATION_SECRET_KEY --output (Join-Path $Evidence "rollback-a-bucket-inventory.v1.json")
Assert-LastExitCode "Rollback a-bucket inventory failed"
python $EvidenceCli compare-objects --expected (Join-Path $Evidence "cutover-source-a-bucket.v1.json") --actual (Join-Path $Evidence "rollback-a-bucket-inventory.v1.json") --output (Join-Path $Evidence "rollback-a-bucket-comparison.v1.json")
Assert-LastExitCode "Rollback a-bucket inventory differs"
python $EvidenceCli milvus-inventory --endpoint http://127.0.0.1:19530 --database reverse1999_rag --output (Join-Path $Evidence "rollback-milvus-inventory.v1.json")
Assert-LastExitCode "Rollback Milvus inventory failed"
python $EvidenceCli compare-milvus --expected (Join-Path $Evidence "milvus-before.v1.json") --actual (Join-Path $Evidence "rollback-milvus-inventory.v1.json") --output (Join-Path $Evidence "rollback-milvus-comparison.v1.json")
Assert-LastExitCode "Rollback Milvus inventory differs"
python $EvidenceCli media-samples --inventory (Join-Path $Evidence "rollback-minio-inventory.v1.json") --base-url http://127.0.0.1:9002/reverse1999-assets --asset-type voice --asset-type image --asset-type portrait --asset-type skill --output (Join-Path $Evidence "rollback-media-samples.v1.json")
Assert-LastExitCode "Rollback media samples failed"
python $EvidenceCli receipt --schema evb.minio-migration-rollback/v1 --status rollback_complete --input "minio=$(Join-Path $Evidence 'rollback-minio-comparison.v1.json')" --input "a_bucket=$(Join-Path $Evidence 'rollback-a-bucket-comparison.v1.json')" --input "milvus=$(Join-Path $Evidence 'rollback-milvus-comparison.v1.json')" --input "media=$(Join-Path $Evidence 'rollback-media-samples.v1.json')" --field "failed_gate=$FailedGate" --field old_image=minio/minio:RELEASE.2023-03-20T20-16-18Z --field endpoint=127.0.0.1:9002 --output (Join-Path $Evidence "rollback.v1.json")
Assert-LastExitCode "Rollback receipt failed"
