<#
.SYNOPSIS
  Update Famulus DMS (Docker): back up the database, fetch the new version, restart, check.

.DESCRIPTION
  Steps: determine the running version -> back up the database to .\backups (the latest 5 are kept)
  -> fetch the new version -> restart the containers -> wait until Famulus DMS answers again.

  Where the new version comes from depends on APP_IMAGE in .env:
  - registry image (e.g. ghcr.io/...): "docker compose pull" fetches the finished image.
  - otherwise (default "homedms/backend"): build from the folder; in a Git folder "git pull" runs first.
    If you replaced the folder by hand, it is simply built again.

  Data, documents and the search index live in Docker volumes or folders and stay untouched.
  Database changes of the new version run automatically at start.
  Going back and restoring: docs/Updates.md.

  Language: the scripts update.de.cmd, update.en.cmd and update.ru.cmd set it; update.cmd and update.ps1 choose
  it from the Windows display language (-Language auto|de|en|ru). All texts: scripts\lang\update.<language>.msg.

.PARAMETER BackupOnly
  Only back up the database, update nothing. (German alias: -NurSichern)
.PARAMETER NoBackup
  Skip the backup (not recommended). (German alias: -OhneSicherung)
.PARAMETER Keep
  So many backups stay in .\backups. (German alias: -Behalten)
.PARAMETER TimeoutSeconds
  So long Famulus DMS gets to answer after the restart. (German alias: -TimeoutSekunden)

.EXAMPLE
  .\scripts\update.cmd

.EXAMPLE
  .\scripts\update.en.cmd -BackupOnly
#>
[CmdletBinding(PositionalBinding = $false)]
param(
  [Alias("NurSichern")][switch]$BackupOnly,
  [Alias("OhneSicherung")][switch]$NoBackup,
  [Alias("Behalten")][int]$Keep = 5,
  [Alias("TimeoutSekunden")][int]$TimeoutSeconds = 300,
  [ValidateSet("auto", "de", "en", "ru")][string]$Language = "auto"
)

# "Continue": Docker writes progress to stderr - that must not be an error. We check the exit codes instead.
$ErrorActionPreference = 'Continue'
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }   # show umlauts / Cyrillic correctly
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# --- Messages (scripts\lang\update.<language>.msg; same loader as install-windows.ps1) -------------
function Import-Messages([string]$Code) {
  $messages = @{}
  $file = Join-Path (Join-Path $PSScriptRoot "lang") "update.$Code.msg"
  if (Test-Path $file) {
    foreach ($line in [IO.File]::ReadAllLines($file, [Text.Encoding]::UTF8)) {
      if ($line -match "^\s*(\w+)\s*=\s*'((?:[^']|'')*)'\s*$") { $messages[$Matches[1]] = $Matches[2].Replace("''", "'") }
    }
  }
  return $messages
}
function Get-UpdateLanguage([string]$Requested) {
  if ($Requested -ne "auto") { return $Requested }
  $code = (Get-UICulture).TwoLetterISOLanguageName
  if ($code -in "de", "ru") { return $code }
  return "en"
}
$Messages = Import-Messages (Get-UpdateLanguage $Language)
$FallbackMessages = Import-Messages "en"
function T {
  param([string]$Key, [Parameter(ValueFromRemainingArguments = $true)]$FormatArgs)
  $text = $script:Messages[$Key]
  if (-not $text) { $text = $script:FallbackMessages[$Key] }
  if (-not $text) { return $Key }
  # @(...): the remaining arguments arrive as a list, which -f would take for ONE argument
  if ($FormatArgs) { $text = $text -f @($FormatArgs) }
  return $text
}

function Fail([string]$message) {
  Write-Host ""
  Write-Host ((T 'label_error') + " $message") -ForegroundColor Red
  exit 1
}

function Step([string]$text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }

function Get-EnvValue([string]$name) {
  if (-not (Test-Path .env)) { return "" }
  $line = Get-Content .env | Where-Object { $_ -match "^\s*$name=" } | Select-Object -First 1
  if (-not $line) { return "" }
  return (($line -replace "^\s*$name=", '') -replace '\s+#.*$', '').Trim().Trim('"').Trim("'")
}

# --- Prerequisites -------------------------------------------------------------------------------
docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail (T 'fail_docker_windows') }
if (-not (Test-Path docker-compose.yml)) { Fail (T 'fail_compose' $root) }

$dbId = (docker compose ps -q db) 2>$null
if (-not $dbId) { Fail (T 'fail_db_down') }

# --- 1. Current version --------------------------------------------------------------------------
Step (T 'step_version')
$before = (docker compose exec -T app-api python -c "import homedms; print(homedms.__version__)") 2>$null
if ($LASTEXITCODE -ne 0 -or -not $before) { $before = "" }
$before = "$before".Trim()
$beforeShown = if ($before) { $before } else { T 'word_unknown' }
Write-Host (T 'info_current' $beforeShown)

# --- 2. Back up the database ---------------------------------------------------------------------
$dump = $null
if ($NoBackup -and -not $BackupOnly) {
  Write-Host (T 'info_backup_skipped' '-NoBackup') -ForegroundColor Yellow
} else {
  Step (T 'step_backup')
  New-Item -ItemType Directory -Force backups | Out-Null
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $versionPart = if ($before) { $before } else { "unknown" }   # fixed word: the file name must not depend on the language
  $dump = Join-Path $root "backups\homedms-$versionPart-$stamp.dump"
  # Write to a file inside the container and copy it out: through the PowerShell pipeline the binary
  # file would be corrupted.
  docker compose exec -T db sh -c 'pg_dump -U $POSTGRES_USER -Fc $POSTGRES_DB -f /tmp/homedms.dump'
  if ($LASTEXITCODE -ne 0) { Fail (T 'fail_backup') }
  docker compose cp db:/tmp/homedms.dump $dump
  $copyOk = ($LASTEXITCODE -eq 0)
  docker compose exec -T db rm -f /tmp/homedms.dump | Out-Null
  if (-not $copyOk -or -not (Test-Path $dump) -or (Get-Item $dump).Length -lt 1024) { Fail (T 'fail_backup_incomplete') }
  Write-Host (T 'info_backup_done' $dump)
  Get-ChildItem backups -Filter 'homedms-*.dump' | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $Keep | Remove-Item -Force
}
if ($BackupOnly) { Write-Host ""; Write-Host (T 'done_backup_only') -ForegroundColor Green; exit 0 }

# --- 3. Fetch the new version --------------------------------------------------------------------
$image = Get-EnvValue 'APP_IMAGE'
if (-not $image) { $image = 'ghcr.io/sschneidt/famulus-dms' }  # default from docker-compose.yml
$fromRegistry = $image -match '^[^/]+[.:][^/]*/'
if ($fromRegistry) {
  Step (T 'step_pull' $image)
  docker compose pull app-api app-worker
  if ($LASTEXITCODE -ne 0) { Fail (T 'fail_pull') }
} else {
  if ((Test-Path .git) -and (Get-Command git -ErrorAction SilentlyContinue)) {
    Step (T 'step_git')
    git pull --ff-only
    if ($LASTEXITCODE -ne 0) { Fail (T 'fail_git') }
  } else {
    Write-Host (T 'info_no_git') -ForegroundColor Yellow
  }
}

# --- 4. Restart ----------------------------------------------------------------------------------
Step (T 'step_restart')
if ($fromRegistry) { docker compose up -d } else { docker compose up -d --build }
if ($LASTEXITCODE -ne 0) { Fail (T 'fail_restart') }

# --- 5. Wait until Famulus DMS answers -----------------------------------------------------------
Step (T 'step_wait')
$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$health = ""
while ((Get-Date) -lt $deadline) {
  $apiId = (docker compose ps -q app-api) 2>$null
  if ($apiId) { $health = (docker inspect -f '{{.State.Health.Status}}' $apiId) 2>$null }
  if ($health -eq 'healthy') { break }
  Start-Sleep -Seconds 3
}
if ($health -ne 'healthy') {
  docker compose logs --tail 40 app-api
  Write-Host ""
  Write-Host (T 'warn_not_ready' $TimeoutSeconds $health) -ForegroundColor Red
  if ($dump) { Write-Host (T 'info_dump_location' $dump) }
  Write-Host (T 'info_rollback')
  exit 1
}

$after = (docker compose exec -T app-api python -c "import homedms; print(homedms.__version__)") 2>$null
$afterShown = if ("$after".Trim()) { "$after".Trim() } else { T 'word_unknown' }
Write-Host ""
Write-Host (T 'done_update' $beforeShown $afterShown) -ForegroundColor Green
