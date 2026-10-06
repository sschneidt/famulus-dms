<#
.SYNOPSIS
  Famulus DMS auf einem Windows-PC installieren – ohne Docker und ohne NAS.

.DESCRIPTION
  PowerShell ALS ADMINISTRATOR öffnen, in den Famulus-DMS-Ordner wechseln und starten:

    powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1

  Optionen:
    -DatenOrdner D:\HomeDMS-Daten   wo Dokumente, Scan-Ordner und Protokolle liegen (Standard C:\HomeDMS-Daten)
    -Port 8000                      Adresse im Browser: http://<PC>:8000
    -OhneKI                         ohne Ollama (keine automatische Einordnung)
    -MitSuche                       zusätzlich Meilisearch (tippfehlertolerante Suche; unter Windows
                                    vom Hersteller nur eingeschränkt unterstützt, daher optional)

  Was passiert (alles mit winget bzw. aus den offiziellen Download-Quellen):
    1. PostgreSQL 16, Tesseract (+ Deutsch), Ollama + Sprachmodelle
    2. In <Famulus DMS>\.tools: uv + Python 3.12, Node.js (nur zum Bauen der Oberfläche), ggf. Meilisearch
    3. Datenbank "homedms" mit eigenem Benutzer und Zufallspasswort
    4. Einstellungen homedms.env (Zufallsschlüssel)
    5. Autostart: geplante Aufgabe "HomeDMS" (startet beim Hochfahren, auch ohne Anmeldung)
    6. Windows-Firewall: Port für das Heimnetz freigeben (Zugriff vom Handy)

  Das Skript kann jederzeit erneut laufen (z. B. nach einem Update des Famulus-DMS-Ordners):
  Vorhandene Einstellungen, Datenbank und Dokumente bleiben unberührt.
#>
[CmdletBinding()]
param(
    [string]$DatenOrdner = "$env:SystemDrive\HomeDMS-Daten",
    [int]$Port = 8000,
    [int]$HttpsPort = 8443,
    [switch]$OhneKI,
    [switch]$MitSuche
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest ist mit Fortschrittsbalken sehr langsam
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$AppDir = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $AppDir ".tools"
$EnvFile = Join-Path $AppDir "homedms.env"
$NodeMajor = 22
$MeiliVersion = "v1.10.3"   # wie im Docker-Betrieb (getmeili/meilisearch:v1.10)
$ChatModel = "llama3.2:3b"
$EmbedModel = "nomic-embed-text"
$TaskName = "HomeDMS"

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Warn($text) { Write-Host "!! $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host "Fehler: $text" -ForegroundColor Red; exit 1 }
function New-Secret([int]$Length = 40) {
    $chars = [char[]]"ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    $bytes = New-Object byte[] $Length
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}
function Slash($path) { $path -replace '\\', '/' }   # homedms.env: Pfade mit / schreiben
function Write-Utf8($path, $text) { [IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding $false)) }
function Invoke-Winget([string]$Id, [string]$Override = "") {
    $wingetArgs = @("install", "--id", $Id, "--exact", "--silent", "--accept-package-agreements", "--accept-source-agreements")
    if ($Override) { $wingetArgs += @("--override", $Override) }
    & winget @wingetArgs
    # -1978335189 = schon installiert - kein Fehler
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) { Fail "winget konnte $Id nicht installieren (Code $LASTEXITCODE)" }
}
function Find-First([string[]]$patterns) {
    foreach ($p in $patterns) {
        $hit = Get-ChildItem -Path $p -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

# --- Voraussetzungen ---------------------------------------------------------------------------
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail "Bitte PowerShell als Administrator starten (Rechtsklick > Als Administrator ausführen)."
}
if (-not (Test-Path (Join-Path $AppDir "backend\pyproject.toml"))) { Fail "$AppDir sieht nicht wie der Famulus-DMS-Ordner aus." }
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Fail "winget fehlt - 'App-Installer' aus dem Microsoft Store installieren (ab Windows 10 21H2 meist schon vorhanden)."
}
if (-not [Environment]::Is64BitOperatingSystem) { Fail "Nur 64-Bit-Windows wird unterstützt." }
New-Item -ItemType Directory -Force -Path $Tools, $DatenOrdner | Out-Null
foreach ($sub in "documents", "scan", "logs", "meilisearch", "tls") { New-Item -ItemType Directory -Force -Path (Join-Path $DatenOrdner $sub) | Out-Null }

# --- 1. PostgreSQL -----------------------------------------------------------------------------
Step "PostgreSQL"
$psql = Find-First @("$env:ProgramFiles\PostgreSQL\*\bin\psql.exe")
$superFile = Join-Path $DatenOrdner "postgres-admin-passwort.txt"
if (-not $psql) {
    $superPassword = New-Secret 24
    Invoke-Winget "PostgreSQL.PostgreSQL.16" "--mode unattended --unattendedmodeui none --superpassword $superPassword --serverport 5432"
    $psql = Find-First @("$env:ProgramFiles\PostgreSQL\*\bin\psql.exe")
    if (-not $psql) { Fail "PostgreSQL wurde nicht gefunden (erwartet unter $env:ProgramFiles\PostgreSQL)." }
    Write-Utf8 $superFile $superPassword
    # Nur Administratoren und SYSTEM dürfen das Datenbank-Admin-Passwort lesen
    icacls $superFile /inheritance:r /grant:r "*S-1-5-32-544:F" "*S-1-5-18:F" | Out-Null
    Write-Host "   Passwort des Datenbank-Admins (postgres): $superFile"
} elseif (Test-Path $superFile) {
    $superPassword = (Get-Content $superFile -Raw).Trim()
} else {
    $secure = Read-Host "PostgreSQL ist schon installiert. Passwort des Benutzers 'postgres'" -AsSecureString
    $superPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}
Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue | Where-Object Status -ne Running | Start-Service

# --- Tesseract ---------------------------------------------------------------------------------
Step "Tesseract (Texterkennung)"
$tesseract = Find-First @("$env:ProgramFiles\Tesseract-OCR\tesseract.exe", "${env:ProgramFiles(x86)}\Tesseract-OCR\tesseract.exe")
if (-not $tesseract) {
    Invoke-Winget "UB-Mannheim.TesseractOCR"
    $tesseract = Find-First @("$env:ProgramFiles\Tesseract-OCR\tesseract.exe", "${env:ProgramFiles(x86)}\Tesseract-OCR\tesseract.exe")
    if (-not $tesseract) { Fail "Tesseract wurde nicht gefunden." }
}
$tessdata = Join-Path (Split-Path $tesseract) "tessdata"
foreach ($lang in "deu", "eng", "rus", "osd") {
    $file = Join-Path $tessdata "$lang.traineddata"
    if (-not (Test-Path $file)) {
        Write-Host "   Sprachpaket $lang laden"
        Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/tesseract-ocr/tessdata/raw/main/$lang.traineddata" -OutFile $file
    }
}

# --- Ollama ------------------------------------------------------------------------------------
if (-not $OhneKI) {
    Step "Ollama (lokale KI)"
    $ollama = Find-First @("$env:LOCALAPPDATA\Programs\Ollama\ollama.exe", "$env:ProgramFiles\Ollama\ollama.exe")
    if (-not $ollama) {
        Invoke-Winget "Ollama.Ollama"
        $ollama = Find-First @("$env:LOCALAPPDATA\Programs\Ollama\ollama.exe", "$env:ProgramFiles\Ollama\ollama.exe")
    }
    if ($ollama) {
        try { Invoke-RestMethod -Uri "http://localhost:11434/api/version" -TimeoutSec 3 | Out-Null }
        catch { Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden; Start-Sleep -Seconds 5 }
        Write-Host "   Sprachmodelle laden ($ChatModel, $EmbedModel) - beim ersten Mal einige GB"
        & $ollama pull $ChatModel
        & $ollama pull $EmbedModel
        if ($LASTEXITCODE -ne 0) { Warn "Modelle konnten nicht geladen werden - später: ollama pull $ChatModel" }
    } else {
        Warn "Ollama wurde nicht gefunden - Famulus DMS läuft, die KI-Einordnung bleibt aber aus."
    }
}

# --- 2. Werkzeuge: uv/Python, Node, Meilisearch --------------------------------------------------
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Tools "python"
$env:UV_CACHE_DIR = Join-Path $Tools "uv-cache"
$env:UV_LINK_MODE = "copy"
$uv = Join-Path $Tools "uv.exe"
if (-not (Test-Path $uv)) {
    Step "uv (Python-Paketverwaltung) laden"
    $env:UV_INSTALL_DIR = $Tools
    $env:UV_NO_MODIFY_PATH = "1"
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
}
Step "Python-Umgebung einrichten (backend\.venv)"
Push-Location (Join-Path $AppDir "backend")
try {
    & $uv sync --frozen --no-dev --python 3.12 --quiet
    if ($LASTEXITCODE -ne 0) { Fail "uv sync fehlgeschlagen" }
} finally { Pop-Location }

$nodeDir = $null
$systemNode = Get-Command node -ErrorAction SilentlyContinue
if ($systemNode -and [int](& node -p "process.versions.node.split('.')[0]") -ge $NodeMajor) {
    $nodeDir = Split-Path $systemNode.Source
} else {
    $nodeDir = Join-Path $Tools "node"
    if (-not (Test-Path (Join-Path $nodeDir "node.exe"))) {
        Step "Node.js $NodeMajor laden (nur zum Bauen der Weboberfläche)"
        $base = "https://nodejs.org/dist/latest-v$NodeMajor.x"
        $zipName = ((Invoke-WebRequest -UseBasicParsing "$base/SHASUMS256.txt").Content -split "`n" |
            Select-String -Pattern "node-v[\d.]+-win-x64\.zip" | Select-Object -First 1).Matches[0].Value
        $zip = Join-Path $Tools $zipName
        Invoke-WebRequest -UseBasicParsing -Uri "$base/$zipName" -OutFile $zip
        Expand-Archive -Path $zip -DestinationPath $Tools -Force
        if (Test-Path $nodeDir) { Remove-Item -Recurse -Force $nodeDir }
        Rename-Item (Join-Path $Tools ($zipName -replace '\.zip$', '')) "node"
        Remove-Item $zip
    }
}
Step "Weboberfläche bauen"
$env:Path = "$nodeDir;$env:Path"
Push-Location (Join-Path $AppDir "frontend")
try {
    & (Join-Path $nodeDir "npm.cmd") ci --no-audit --no-fund --silent
    if ($LASTEXITCODE -ne 0) { Fail "npm ci fehlgeschlagen" }
    & (Join-Path $nodeDir "npm.cmd") run build --silent | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "Bauen der Weboberfläche fehlgeschlagen" }
} finally { Pop-Location }

$meiliExe = ""
if ($MitSuche) {
    $meiliExe = Join-Path $Tools "meilisearch-$MeiliVersion.exe"
    if (-not (Test-Path $meiliExe)) {
        Step "Meilisearch $MeiliVersion laden"
        Invoke-WebRequest -UseBasicParsing -OutFile $meiliExe `
            -Uri "https://github.com/meilisearch/meilisearch/releases/download/$MeiliVersion/meilisearch-windows-amd64.exe"
    }
}

# --- 3./4. Einstellungen + Datenbank -------------------------------------------------------------
if (-not (Test-Path $EnvFile)) {
    Step "Einstellungen anlegen ($EnvFile)"
    $dbPassword = New-Secret 32
    $text = Get-Content (Join-Path $AppDir "homedms.env.example") -Raw
    $values = @{
        "DATABASE_URL"     = "postgresql://homedms:$dbPassword@localhost:5432/homedms"
        "JWT_SECRET"       = New-Secret 64
        "MEILISEARCH_KEY"  = New-Secret 40
        "DOCUMENTS_PATH"   = Slash (Join-Path $DatenOrdner "documents")
        "SCAN_PATH"        = Slash (Join-Path $DatenOrdner "scan")
        "LOG_DIR"          = Slash (Join-Path $DatenOrdner "logs")
        "MEILISEARCH_DATA" = Slash (Join-Path $DatenOrdner "meilisearch")
        "TESSERACT_CMD"    = Slash $tesseract
        "PORT"             = "$Port"
        "HTTPS_PORT"       = "$HttpsPort"
        "TLS_DIR"          = Slash (Join-Path $DatenOrdner "tls")
        "TESSDATA_DIR"     = Slash (Join-Path $DatenOrdner "tessdata")
        "SETUP_CODE"       = ((New-Secret 12) -replace '(.{4})(?!$)', '$1-').ToUpper()
    }
    foreach ($key in $values.Keys) { $text = [regex]::Replace($text, "(?m)^$key=.*$", "$key=$($values[$key])") }
    Write-Utf8 $EnvFile $text
} else {
    $dbPassword = ([regex]::Match((Get-Content $EnvFile -Raw), "(?m)^DATABASE_URL=postgresql://[^:]*:([^@]*)@")).Groups[1].Value
}
# Suche an-/abschalten je nach Option
$text = Get-Content $EnvFile -Raw
if ($MitSuche) {
    $text = [regex]::Replace($text, "(?m)^MEILISEARCH_BINARY=.*$", "MEILISEARCH_BINARY=$(Slash $meiliExe)")
    $text = [regex]::Replace($text, "(?m)^MEILISEARCH_URL=[ \t\r]*$", "MEILISEARCH_URL=http://127.0.0.1:7700")
} else {
    $text = [regex]::Replace($text, "(?m)^MEILISEARCH_BINARY=.*$", "MEILISEARCH_BINARY=")
    $text = [regex]::Replace($text, "(?m)^MEILISEARCH_URL=.*$", "MEILISEARCH_URL=")
}
Write-Utf8 $EnvFile $text
icacls $EnvFile /inheritance:r /grant:r "*S-1-5-32-544:F" "*S-1-5-18:F" | Out-Null   # nur Admins + SYSTEM

Step "Datenbank einrichten"
$env:PGPASSWORD = $superPassword
function Invoke-Psql([string]$Sql, [string]$Database = "postgres") {
    $out = & $psql -U postgres -h localhost -d $Database -tAc $Sql
    if ($LASTEXITCODE -ne 0) { Fail "Datenbank-Befehl fehlgeschlagen (Passwort von 'postgres' richtig?)" }
    return $out
}
if ((Invoke-Psql "SELECT 1 FROM pg_roles WHERE rolname='homedms'") -ne "1") {
    Invoke-Psql "CREATE ROLE homedms LOGIN PASSWORD '$dbPassword'" | Out-Null
}
if ((Invoke-Psql "SELECT 1 FROM pg_database WHERE datname='homedms'") -ne "1") {
    Invoke-Psql "CREATE DATABASE homedms OWNER homedms ENCODING 'UTF8' TEMPLATE template0" | Out-Null
}
Invoke-Psql "CREATE EXTENSION IF NOT EXISTS pg_trgm" "homedms" | Out-Null
Remove-Item Env:PGPASSWORD

# --- 5. Autostart + 6. Firewall ------------------------------------------------------------------
Step "Autostart einrichten (geplante Aufgabe '$TaskName')"
$python = Join-Path $AppDir "backend\.venv\Scripts\python.exe"
$action = New-ScheduledTaskAction -Execute $python -Argument "-m homedms.server" -WorkingDirectory (Join-Path $AppDir "backend")
$trigger = New-ScheduledTaskTrigger -AtStartup
$principalTask = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principalTask -Settings $settings `
    -Description "Famulus DMS - Dokumentenverwaltung (Weboberfläche, Texterkennung, KI)" -Force | Out-Null
# Laufende Reste eines früheren Starts beenden, dann neu starten
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*homedms.*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-ScheduledTask -TaskName $TaskName

Step "Firewall: Ports $Port und $HttpsPort im Heimnetz freigeben"
Get-NetFirewallRule -DisplayName "HomeDMS" -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName "HomeDMS" -Direction Inbound -Protocol TCP -LocalPort $Port, $HttpsPort -Profile Private, Domain -Action Allow | Out-Null

$ok = $false
for ($i = 0; $i -lt 90; $i++) {
    try { Invoke-RestMethod -Uri "http://localhost:$Port/health" -TimeoutSec 2 | Out-Null; $ok = $true; break } catch { Start-Sleep -Seconds 1 }
}
if (-not $ok) { Fail "Famulus DMS antwortet nicht - Protokoll: $(Join-Path $DatenOrdner 'logs\homedms.log')" }

# Diesem PC gleich vertrauen (die anderen Geraete: Seite /zertifikat)
$caFile = Join-Path $DatenOrdner "tls\ca.crt"
if (Test-Path $caFile) {
    Import-Certificate -FilePath $caFile -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
    Write-Host "   Zertifikat der Famulus-DMS-Zertifizierungsstelle auf diesem PC als vertrauenswürdig eingetragen."
}
$ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.PrefixOrigin -in "Dhcp", "Manual" -and $_.IPAddress -notlike "169.*" } | Select-Object -First 1).IPAddress
Step "Fertig! Famulus DMS läuft: https://localhost:$HttpsPort  (im Heimnetz: https://$($ip):$HttpsPort)"
Write-Host "   Handy und andere PCs: einmal http://$($ip):$Port/zertifikat öffnen und dem Zertifikat vertrauen."
$setupCode = ([regex]::Match((Get-Content $EnvFile -Raw), "(?m)^SETUP_CODE=(\S+)")).Groups[1].Value
Write-Host "   Beim ersten Aufruf führt ein Assistent durch die Einrichtung (Haushalt + Admin-Konto)."
if ($setupCode) { Write-Host "   Einrichtungscode: $setupCode" -ForegroundColor Green }
Write-Host "   Dokumente: $(Join-Path $DatenOrdner 'documents')   Scan-Ordner: $(Join-Path $DatenOrdner 'scan')"
Write-Host "   Protokoll: $(Join-Path $DatenOrdner 'logs')   Autostart: Aufgabenplanung > '$TaskName'"
if (-not $OhneKI) { Write-Host "   Hinweis: Ollama läuft unter Windows im angemeldeten Benutzer - nach einem Neustart erst nach der Anmeldung." }
Start-Process "https://localhost:$HttpsPort"
