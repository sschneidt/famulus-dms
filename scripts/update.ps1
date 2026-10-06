<#
.SYNOPSIS
  Famulus DMS aktualisieren (Docker): Datenbank sichern, neue Version holen, neu starten, pruefen.

.DESCRIPTION
  Schritte: laufende Version feststellen -> Datenbank nach .\backups sichern (die letzten 5 bleiben)
  -> neue Version holen -> Container neu starten -> warten, bis Famulus DMS wieder antwortet.

  Woher die neue Version kommt, entscheidet APP_IMAGE in der .env:
  - Registry-Image (z. B. ghcr.io/...): "docker compose pull" holt das fertige Image.
  - sonst (Standard "homedms/backend"): aus dem Ordner bauen; ist er ein Git-Ordner, wird vorher
    "git pull" ausgefuehrt. Hast du den Ordner von Hand ersetzt, wird einfach neu gebaut.

  Daten, Dokumente und Suchindex liegen in Docker-Volumes bzw. Ordnern und bleiben unberuehrt.
  Datenbank-Aenderungen der neuen Version laufen beim Start automatisch.
  Zurueckgehen und Wiederherstellen: docs/Updates.md.

.EXAMPLE
  .\scripts\update.cmd

.EXAMPLE
  .\scripts\update.cmd -NurSichern
#>
[CmdletBinding(PositionalBinding = $false)]
param(
  [switch]$NurSichern,        # nur die Datenbank sichern, nichts aktualisieren
  [switch]$OhneSicherung,     # Sicherung ueberspringen (nicht empfohlen)
  [int]$Behalten = 5,         # so viele Sicherungen bleiben liegen
  [int]$TimeoutSekunden = 300 # so lange wird auf den Neustart gewartet
)

# "Continue": Docker schreibt Fortschritt nach stderr - das darf kein Fehler sein. Fehler pruefen wir
# ueber den Exit-Code.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

function Fail([string]$message) {
  Write-Host ""
  Write-Host "FEHLER: $message" -ForegroundColor Red
  exit 1
}

function Step([string]$text) { Write-Host ""; Write-Host "==> $text" -ForegroundColor Cyan }

function Get-EnvValue([string]$name) {
  if (-not (Test-Path .env)) { return "" }
  $line = Get-Content .env | Where-Object { $_ -match "^\s*$name=" } | Select-Object -First 1
  if (-not $line) { return "" }
  return (($line -replace "^\s*$name=", '') -replace '\s+#.*$', '').Trim().Trim('"').Trim("'")
}

# --- Voraussetzungen ---------------------------------------------------------------------------
docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail "Docker laeuft nicht. Bitte Docker Desktop starten und noch einmal versuchen." }
if (-not (Test-Path docker-compose.yml)) { Fail "docker-compose.yml nicht gefunden (erwartet in $root)." }

$dbId = (docker compose ps -q db) 2>$null
if (-not $dbId) { Fail "Der Datenbank-Container laeuft nicht. Erst mit 'docker compose up -d' starten." }

# --- 1. Aktuelle Version -----------------------------------------------------------------------
Step "Installierte Version feststellen"
$before = (docker compose exec -T app-api python -c "import homedms; print(homedms.__version__)") 2>$null
if ($LASTEXITCODE -ne 0 -or -not $before) { $before = "unbekannt" }
$before = "$before".Trim()
Write-Host "Aktuell: $before"

# --- 2. Datenbank sichern ----------------------------------------------------------------------
$dump = $null
if ($OhneSicherung -and -not $NurSichern) {
  Write-Host "Sicherung uebersprungen (-OhneSicherung)." -ForegroundColor Yellow
} else {
  Step "Datenbank sichern"
  New-Item -ItemType Directory -Force backups | Out-Null
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $dump = Join-Path $root "backups\homedms-$before-$stamp.dump"
  # Im Container in eine Datei schreiben und dann herauskopieren: ueber die PowerShell-Pipeline
  # wuerde die Binaerdatei beschaedigt.
  docker compose exec -T db sh -c 'pg_dump -U $POSTGRES_USER -Fc $POSTGRES_DB -f /tmp/homedms.dump'
  if ($LASTEXITCODE -ne 0) { Fail "Die Datenbank konnte nicht gesichert werden. Es wurde nichts veraendert." }
  docker compose cp db:/tmp/homedms.dump $dump
  $copyOk = ($LASTEXITCODE -eq 0)
  docker compose exec -T db rm -f /tmp/homedms.dump | Out-Null
  if (-not $copyOk -or -not (Test-Path $dump) -or (Get-Item $dump).Length -lt 1024) {
    Fail "Die Sicherung ist unvollstaendig. Es wurde nichts veraendert."
  }
  Write-Host ("Gesichert: {0} ({1:N1} MB)" -f $dump, ((Get-Item $dump).Length / 1MB))
  Get-ChildItem backups -Filter 'homedms-*.dump' | Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $Behalten | Remove-Item -Force
}
if ($NurSichern) { Write-Host ""; Write-Host "Fertig (nur gesichert)." -ForegroundColor Green; exit 0 }

# --- 3. Neue Version holen ---------------------------------------------------------------------
$image = Get-EnvValue 'APP_IMAGE'
if (-not $image) { $image = 'ghcr.io/sschneidt/famulus-dms' }  # Standard aus docker-compose.yml
$fromRegistry = $image -match '^[^/]+[.:][^/]*/'
if ($fromRegistry) {
  Step "Neue Version herunterladen ($image)"
  docker compose pull app-api app-worker
  if ($LASTEXITCODE -ne 0) { Fail "Das Image konnte nicht geladen werden. Es laeuft weiter die bisherige Version." }
} else {
  if ((Test-Path .git) -and (Get-Command git -ErrorAction SilentlyContinue)) {
    Step "Neuen Stand holen (git pull)"
    git pull --ff-only
    if ($LASTEXITCODE -ne 0) { Fail "git pull ist fehlgeschlagen (lokale Aenderungen?). Es laeuft weiter die bisherige Version." }
  } else {
    Write-Host "Kein Git-Ordner - es wird der Stand im Ordner gebaut." -ForegroundColor Yellow
  }
}

# --- 4. Neu starten ----------------------------------------------------------------------------
Step "Famulus DMS neu starten"
if ($fromRegistry) { docker compose up -d } else { docker compose up -d --build }
if ($LASTEXITCODE -ne 0) { Fail "Der Neustart ist fehlgeschlagen." }

# --- 5. Warten, bis Famulus DMS antwortet ----------------------------------------------------------
Step "Warten, bis Famulus DMS wieder antwortet"
$deadline = (Get-Date).AddSeconds($TimeoutSekunden)
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
  Write-Host "Famulus DMS ist nach $TimeoutSekunden Sekunden nicht bereit (Status: $health)." -ForegroundColor Red
  if ($dump) { Write-Host "Deine Datenbank-Sicherung liegt in: $dump" }
  Write-Host "So geht es zurueck: docs/Updates.md, Abschnitt 'Zurueck zur alten Version'."
  exit 1
}

$after = (docker compose exec -T app-api python -c "import homedms; print(homedms.__version__)") 2>$null
Write-Host ""
Write-Host "Fertig. Version: $("$before".Trim()) -> $("$after".Trim())" -ForegroundColor Green
