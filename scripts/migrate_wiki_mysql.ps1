param(
  [string]$SourceContainer = "edurag-mysql",
  [string]$TargetContainer = "reverse1999-main-mysql",
  [string]$Database = "reverse1999_wiki",
  [string]$SourceRootPassword = "",
  [string]$TargetRootPassword = ""
)

$ErrorActionPreference = "Stop"
$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$backupDir = Join-Path $projectRoot "backups\wiki-mysql"
New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$dumpPath = Join-Path $backupDir "$Database-$stamp.sql"

function Get-ContainerEnvValue {
  param(
    [string]$Container,
    [string]$Name
  )

  $line = docker inspect $Container --format '{{range .Config.Env}}{{println .}}{{end}}' |
    Where-Object { $_ -like "$Name=*" } |
    Select-Object -First 1

  if ([string]::IsNullOrWhiteSpace($line)) {
    return ""
  }

  return $line.Substring($Name.Length + 1)
}

function Resolve-RootPassword {
  param(
    [string]$Container,
    [string]$ProvidedPassword,
    [string]$EnvName
  )

  if (-not [string]::IsNullOrWhiteSpace($ProvidedPassword)) {
    return $ProvidedPassword
  }

  $envPassword = [Environment]::GetEnvironmentVariable($EnvName)
  if (-not [string]::IsNullOrWhiteSpace($envPassword)) {
    return $envPassword
  }

  $containerPassword = Get-ContainerEnvValue -Container $Container -Name "MYSQL_ROOT_PASSWORD"
  if (-not [string]::IsNullOrWhiteSpace($containerPassword)) {
    return $containerPassword
  }

  throw "Root password for $Container is required. Pass a parameter, set $EnvName, or expose MYSQL_ROOT_PASSWORD in the Docker container environment."
}

$SourceRootPassword = Resolve-RootPassword -Container $SourceContainer -ProvidedPassword $SourceRootPassword -EnvName "SOURCE_MYSQL_ROOT_PASSWORD"
$TargetRootPassword = Resolve-RootPassword -Container $TargetContainer -ProvidedPassword $TargetRootPassword -EnvName "MYSQL_ROOT_PASSWORD"

function Invoke-MysqlScalar {
  param(
    [string]$Container,
    [string]$Password,
    [string]$Sql
  )

  $output = docker exec $Container mysql -uroot "-p$Password" -N -B -e $Sql
  return ($output | Select-Object -Last 1).Trim()
}

function Invoke-ProcessChecked {
  param(
    [string]$FilePath,
    [string[]]$ArgumentItems,
    [string]$StandardOutputPath = "",
    [string]$StandardInputPath = ""
  )

  $stderrPath = Join-Path $backupDir "$stamp-$([guid]::NewGuid().ToString('N')).err.log"
  $processArgs = @{
    FilePath = $FilePath
    ArgumentList = $ArgumentItems
    Wait = $true
    PassThru = $true
    NoNewWindow = $true
    RedirectStandardError = $stderrPath
  }
  if (-not [string]::IsNullOrWhiteSpace($StandardOutputPath)) {
    $processArgs.RedirectStandardOutput = $StandardOutputPath
  }
  if (-not [string]::IsNullOrWhiteSpace($StandardInputPath)) {
    $processArgs.RedirectStandardInput = $StandardInputPath
  }

  $process = Start-Process @processArgs
  if ($process.ExitCode -ne 0) {
    $stderr = ""
    if (Test-Path -LiteralPath $stderrPath) {
      $stderr = [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $stderrPath))
    }
    throw "$FilePath exited with code $($process.ExitCode). $stderr"
  }
}

function Get-WikiPageTextSignature {
  param(
    [string]$Container,
    [string]$Password
  )

  $signatureSql = "SET SESSION group_concat_max_len = 10000000; SELECT MD5(COALESCE(GROUP_CONCAT(CONCAT_WS(':', page_id, HEX(title), HEX(subtitle), HEX(category), HEX(route), HEX(source_title)) ORDER BY page_id SEPARATOR '|'), '')) FROM $Database.wiki_pages;"
  return Invoke-MysqlScalar -Container $Container -Password $Password -Sql $signatureSql
}

Write-Host "Checking source database..."
$sourcePages = Invoke-MysqlScalar -Container $SourceContainer -Password $SourceRootPassword -Sql "SELECT COUNT(*) FROM $Database.wiki_pages;"
if ([int]$sourcePages -le 0) {
  throw "Source database $Database has no wiki_pages rows."
}

Write-Host "Dumping $Database from $SourceContainer to $dumpPath"
Invoke-ProcessChecked `
  -FilePath "docker" `
  -ArgumentItems @("exec", $SourceContainer, "mysqldump", "-uroot", "-p$SourceRootPassword", "--single-transaction", "--default-character-set=utf8mb4", $Database) `
  -StandardOutputPath $dumpPath

Write-Host "Creating target database if needed..."
docker exec $TargetContainer mysql -uroot "-p$TargetRootPassword" -e "CREATE DATABASE IF NOT EXISTS $Database CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

Write-Host "Restoring dump into $TargetContainer..."
Invoke-ProcessChecked `
  -FilePath "docker" `
  -ArgumentItems @("exec", "-i", $TargetContainer, "mysql", "-uroot", "-p$TargetRootPassword", $Database) `
  -StandardInputPath $dumpPath

$tables = @("wiki_pages", "wiki_categories", "wiki_media_links", "wiki_link_spans", "wiki_aliases")
foreach ($table in $tables) {
  $sourceCount = Invoke-MysqlScalar -Container $SourceContainer -Password $SourceRootPassword -Sql "SELECT COUNT(*) FROM $Database.$table;"
  $targetCount = Invoke-MysqlScalar -Container $TargetContainer -Password $TargetRootPassword -Sql "SELECT COUNT(*) FROM $Database.$table;"
  Write-Host "$table source=$sourceCount target=$targetCount"
  if ($sourceCount -ne $targetCount) {
    throw "Row count mismatch for $table"
  }
}

$sourceTextSignature = Get-WikiPageTextSignature -Container $SourceContainer -Password $SourceRootPassword
$targetTextSignature = Get-WikiPageTextSignature -Container $TargetContainer -Password $TargetRootPassword
Write-Host "wiki_pages text signature source=$sourceTextSignature target=$targetTextSignature"
if ($sourceTextSignature -ne $targetTextSignature) {
  throw "Text signature mismatch for wiki_pages. Dump/restore did not preserve UTF-8 text."
}

Write-Host "Migration verified. Dump retained at $dumpPath"
