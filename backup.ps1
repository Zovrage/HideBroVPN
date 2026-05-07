param(
    [string]$Service = "postgres",
    [string]$Database = "hidebrovpn",
    [string]$User = "hidebro",
    [string]$OutputDir = "backups",
    [string]$Prefix = "hidebrovpn",
    [switch]$NoCleanup
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$outputPath = Join-Path $projectRoot $OutputDir
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$fileName = "{0}_{1}.dump" -f $Prefix, $timestamp
$localFile = Join-Path $outputPath $fileName
$tmpFile = "/tmp/$fileName"

Write-Host "Creating PostgreSQL backup..."
Write-Host "Service: $Service | DB: $Database | User: $User"

& docker compose exec $Service pg_dump -U $User -d $Database -Fc -f $tmpFile
& docker compose cp "${Service}:$tmpFile" "$localFile"

if (-not $NoCleanup) {
    & docker compose exec $Service rm -f $tmpFile
}

Write-Host "Backup saved to: $localFile"
