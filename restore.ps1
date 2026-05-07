param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [string]$Service = "postgres",
    [string]$Database = "hidebrovpn",
    [string]$User = "hidebro",
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if ([System.IO.Path]::IsPathRooted($BackupFile)) {
    $resolvedBackup = $BackupFile
} else {
    $resolvedBackup = Join-Path $projectRoot $BackupFile
}

if (-not (Test-Path -LiteralPath $resolvedBackup)) {
    throw "Backup file not found: $resolvedBackup"
}

if (-not $Force) {
    Write-Host "WARNING: this will DROP and recreate database '$Database'."
    $answer = Read-Host "Type RESTORE to continue"
    if ($answer -ne "RESTORE") {
        Write-Host "Restore cancelled."
        exit 1
    }
}

$fileName = [System.IO.Path]::GetFileName($resolvedBackup)
$tmpFile = "/tmp/$fileName"
$terminateSql = "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$Database' AND pid <> pg_backend_pid();"

Write-Host "Restoring PostgreSQL backup..."
Write-Host "Service: $Service | DB: $Database | User: $User"

& docker compose cp "$resolvedBackup" "${Service}:$tmpFile"

& docker compose exec $Service psql -U $User -d postgres -c $terminateSql
& docker compose exec $Service dropdb -U $User --if-exists $Database
& docker compose exec $Service createdb -U $User $Database
& docker compose exec $Service pg_restore -U $User -d $Database --clean --if-exists $tmpFile
& docker compose exec $Service rm -f $tmpFile

Write-Host "Restore complete."
