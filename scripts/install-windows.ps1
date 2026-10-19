<#
.SYNOPSIS
  Install Famulus DMS on a Windows PC - without Docker and without a NAS.

.DESCRIPTION
  Open PowerShell AS ADMINISTRATOR, change to the Famulus DMS folder and run ONE of these:

    powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1      language chosen automatically
    powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.en.ps1   English
    powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.de.ps1   Deutsch
    powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ru.ps1   Russian

  The installation runs in the chosen language. The texts live in scripts\lang\install-windows.<language>.msg,
  English is the fallback. The language scripts only set -Language and pass everything else through.

  Options:
    -DataFolder D:\Famulus-Data   where documents, scan folder and logs are stored. Without it the script asks
                                  (proposal: C:\Famulus-Data). An existing installation keeps its folder.
                                  (German alias: -DatenOrdner)
    -Port 8000                    address in the browser: http://<PC>:8000
    -HttpsPort 8443               address in the browser: https://<PC>:8443
    -NoAI                         without Ollama (no automatic classification)   (alias: -OhneKI)
    -WithSearch                   additionally Meilisearch (typo-tolerant search; the vendor supports it on
                                  Windows only in a limited way, hence optional)   (alias: -MitSuche)
    -Language auto|de|en|ru       language of the installation (default: auto = Windows display language,
                                  English if there is no translation)

  What happens (everything via winget or the official download sources):
    1. PostgreSQL 16, Tesseract (+ language packs), Ollama + language models
    2. In <Famulus DMS>\.tools: uv + Python 3.12, Node.js (only to build the web interface), optionally Meilisearch
    3. Database "homedms" with its own user and a random password
    4. Settings file homedms.env (random keys)
    5. Autostart: scheduled task "Famulus DMS" (starts at boot, also without a signed-in user)
    6. Windows Firewall: open the ports for the home network (access from a phone)

  The script can be run again at any time (e.g. after updating the Famulus DMS folder):
  existing settings, database and documents stay untouched.
#>
[CmdletBinding()]
param(
    [Alias("DatenOrdner")][string]$DataFolder = "",
    [int]$Port = 8000,
    [int]$HttpsPort = 8443,
    [Alias("OhneKI")][switch]$NoAI,
    [Alias("MitSuche")][switch]$WithSearch,
    [ValidateSet("auto", "de", "en", "ru")][string]$Language = "auto"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest is very slow with a progress bar
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }   # show umlauts / Cyrillic correctly

$AppDir = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $AppDir ".tools"
$EnvFile = Join-Path $AppDir "homedms.env"
$NodeMajor = 22
$MeiliVersion = "v1.10.3"   # same as in the Docker setup (getmeili/meilisearch:v1.10)
$ChatModel = "llama3.2:3b"
$EmbedModel = "nomic-embed-text"
$TaskName = "Famulus DMS"

# --- Messages ------------------------------------------------------------------------------------
# Every text shown to the user comes from scripts\lang\install-windows.<language>.msg (T 'key' arg0 arg1 ...).
# One text per line: key = 'text' ('' stands for a quote). Read with a small parser instead of
# Import-PowerShellDataFile: that cmdlet is missing when Windows PowerShell is started from PowerShell 7
# (inherited module path), and the parser never runs code from the file.
function Import-Messages([string]$Code) {
    $messages = @{}
    $file = Join-Path (Join-Path $PSScriptRoot "lang") "install-windows.$Code.msg"
    if (Test-Path $file) {
        foreach ($line in [IO.File]::ReadAllLines($file, [Text.Encoding]::UTF8)) {
            if ($line -match "^\s*(\w+)\s*=\s*'((?:[^']|'')*)'\s*$") { $messages[$Matches[1]] = $Matches[2].Replace("''", "'") }
        }
    }
    return $messages
}
function Get-InstallerLanguage([string]$Requested) {
    if ($Requested -ne "auto") { return $Requested }
    $code = (Get-UICulture).TwoLetterISOLanguageName
    if ($code -in "de", "ru") { return $code }
    return "en"
}
$Messages = Import-Messages (Get-InstallerLanguage $Language)
$FallbackMessages = Import-Messages "en"
function T {
    param([string]$Key, [Parameter(ValueFromRemainingArguments = $true)]$FormatArgs)
    $text = $script:Messages[$Key]
    if (-not $text) { $text = $script:FallbackMessages[$Key] }
    if (-not $text) { return $Key }
    # @(...): the remaining arguments arrive as a list, which -f would take for ONE argument ({1} would fail)
    if ($FormatArgs) { $text = $text -f @($FormatArgs) }
    return $text
}

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Warn($text) { Write-Host "!! $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host ((T 'label_error') + " $text") -ForegroundColor Red; exit 1 }
function New-Secret([int]$Length = 40) {
    $chars = [char[]]"ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    $bytes = New-Object byte[] $Length
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}
function Slash($path) { $path -replace '\\', '/' }   # homedms.env: write paths with forward slashes
function Write-Utf8($path, $text) { [IO.File]::WriteAllText($path, $text, (New-Object Text.UTF8Encoding $false)) }
function Invoke-Winget([string]$Id, [string]$Override = "") {
    $wingetArgs = @("install", "--id", $Id, "--exact", "--silent", "--accept-package-agreements", "--accept-source-agreements")
    if ($Override) { $wingetArgs += @("--override", $Override) }
    & winget @wingetArgs
    # -1978335189 = already installed - not an error
    if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335189) { Fail (T 'fail_winget_install' $Id $LASTEXITCODE) }
}
function Read-DataFolder([string]$Default) {
    while ($true) {
        $answer = Read-Host (T 'prompt_data_folder' $Default)
        $path = if ([string]::IsNullOrWhiteSpace($answer)) { $Default } else { $answer.Trim().Trim('"') }
        if ($path.StartsWith("\\") -or -not [IO.Path]::IsPathRooted($path) -or -not [IO.Path]::GetPathRoot($path).Contains(":")) {
            Warn (T 'warn_path_invalid')
            continue
        }
        if (-not (Test-Path ([IO.Path]::GetPathRoot($path)))) { Warn (T 'warn_drive_missing' ([IO.Path]::GetPathRoot($path))); continue }
        $full = [IO.Path]::GetFullPath($path)
        if ($full.Length -gt 3) { $full = $full.TrimEnd('\') }   # no trailing backslash (a bare drive "D:\" stays)
        return $full
    }
}
# Address of this PC in the home network: the IPv4 address of the adapter that has a gateway. Virtual adapters
# (WSL, Hyper-V, Docker) have none - a phone could never reach those addresses.
function Get-LanAddress {
    foreach ($nic in [Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
        if ($nic.OperationalStatus -ne 'Up' -or $nic.NetworkInterfaceType -in 'Loopback', 'Tunnel') { continue }
        $props = $nic.GetIPProperties()
        $gateway = $props.GatewayAddresses | Where-Object { $_.Address.AddressFamily -eq 'InterNetwork' -and $_.Address.ToString() -ne '0.0.0.0' }
        if (-not $gateway) { continue }
        $v4 = $props.UnicastAddresses | Where-Object { $_.Address.AddressFamily -eq 'InterNetwork' } | Select-Object -First 1
        if ($v4) { return $v4.Address.ToString() }
    }
    return $null
}
function Find-First([string[]]$patterns) {
    foreach ($p in $patterns) {
        $hit = Get-ChildItem -Path $p -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}

# --- Prerequisites -------------------------------------------------------------------------------
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail (T 'fail_admin')
}
if (-not (Test-Path (Join-Path $AppDir "backend\pyproject.toml"))) { Fail (T 'fail_appdir' $AppDir) }
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Fail (T 'fail_winget')
}
if (-not [Environment]::Is64BitOperatingSystem) { Fail (T 'fail_64bit') }
# Data folder: -DataFolder > existing installation (homedms.env) > ask, with a proposal
if (-not $DataFolder -and (Test-Path $EnvFile)) {
    $docs = [regex]::Match((Get-Content $EnvFile -Raw), "(?m)^DOCUMENTS_PATH=(\S+)").Groups[1].Value
    if ($docs) { $DataFolder = Split-Path ($docs -replace '/', '\') -Parent; Write-Host (T 'info_existing' $DataFolder) }
}
if (-not $DataFolder) {
    $proposal = "$env:SystemDrive\Famulus-Data"
    if ([Console]::IsInputRedirected) {
        $DataFolder = $proposal
        Warn (T 'warn_no_input' $proposal)
    } else {
        $DataFolder = Read-DataFolder $proposal
    }
}
Write-Host (T 'info_data_folder' $DataFolder)
New-Item -ItemType Directory -Force -Path $Tools, $DataFolder | Out-Null
foreach ($sub in "documents", "scan", "logs", "meilisearch", "tls") { New-Item -ItemType Directory -Force -Path (Join-Path $DataFolder $sub) | Out-Null }

# --- 1. PostgreSQL -------------------------------------------------------------------------------
Step (T 'step_postgres')
$psql = Find-First @("$env:ProgramFiles\PostgreSQL\*\bin\psql.exe")
$superFile = Join-Path $DataFolder "postgres-admin-password.txt"
$legacySuperFile = Join-Path $DataFolder "postgres-admin-passwort.txt"   # name used before the English rename
if (-not (Test-Path $superFile) -and (Test-Path $legacySuperFile)) { $superFile = $legacySuperFile }
if (-not $psql) {
    $superPassword = New-Secret 24
    Invoke-Winget "PostgreSQL.PostgreSQL.16" "--mode unattended --unattendedmodeui none --superpassword $superPassword --serverport 5432"
    $psql = Find-First @("$env:ProgramFiles\PostgreSQL\*\bin\psql.exe")
    if (-not $psql) { Fail (T 'fail_postgres_missing' "$env:ProgramFiles\PostgreSQL") }
    Write-Utf8 $superFile $superPassword
    # Only administrators and SYSTEM may read the database admin password
    icacls $superFile /inheritance:r /grant:r "*S-1-5-32-544:F" "*S-1-5-18:F" | Out-Null
    Write-Host (T 'info_pg_password' $superFile)
} elseif (Test-Path $superFile) {
    $superPassword = (Get-Content $superFile -Raw).Trim()
} else {
    $secure = Read-Host (T 'prompt_postgres_password') -AsSecureString
    $superPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}
Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue | Where-Object Status -ne Running | Start-Service

# --- Tesseract -----------------------------------------------------------------------------------
Step (T 'step_tesseract')
$tesseract = Find-First @("$env:ProgramFiles\Tesseract-OCR\tesseract.exe", "${env:ProgramFiles(x86)}\Tesseract-OCR\tesseract.exe")
if (-not $tesseract) {
    Invoke-Winget "UB-Mannheim.TesseractOCR"
    $tesseract = Find-First @("$env:ProgramFiles\Tesseract-OCR\tesseract.exe", "${env:ProgramFiles(x86)}\Tesseract-OCR\tesseract.exe")
    if (-not $tesseract) { Fail (T 'fail_tesseract_missing') }
}
$tessdata = Join-Path (Split-Path $tesseract) "tessdata"
foreach ($lang in "deu", "eng", "rus", "osd") {
    $file = Join-Path $tessdata "$lang.traineddata"
    if (-not (Test-Path $file)) {
        Write-Host (T 'info_lang_pack' $lang)
        Invoke-WebRequest -UseBasicParsing -Uri "https://github.com/tesseract-ocr/tessdata/raw/main/$lang.traineddata" -OutFile $file
    }
}

# --- Ollama --------------------------------------------------------------------------------------
if (-not $NoAI) {
    Step (T 'step_ollama')
    $ollama = Find-First @("$env:LOCALAPPDATA\Programs\Ollama\ollama.exe", "$env:ProgramFiles\Ollama\ollama.exe")
    if (-not $ollama) {
        Invoke-Winget "Ollama.Ollama"
        $ollama = Find-First @("$env:LOCALAPPDATA\Programs\Ollama\ollama.exe", "$env:ProgramFiles\Ollama\ollama.exe")
    }
    if ($ollama) {
        try { Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 3 | Out-Null }
        catch { Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden; Start-Sleep -Seconds 5 }
        Write-Host (T 'info_models' $ChatModel $EmbedModel)
        & $ollama pull $ChatModel
        & $ollama pull $EmbedModel
        if ($LASTEXITCODE -ne 0) { Warn (T 'warn_models' $ChatModel) }
    } else {
        Warn (T 'warn_ollama_missing')
    }
}

# --- 2. Tools: uv/Python, Node, Meilisearch ------------------------------------------------------
$env:UV_PYTHON_INSTALL_DIR = Join-Path $Tools "python"
$env:UV_CACHE_DIR = Join-Path $Tools "uv-cache"
$env:UV_LINK_MODE = "copy"
$uv = Join-Path $Tools "uv.exe"
if (-not (Test-Path $uv)) {
    Step (T 'step_uv')
    $env:UV_INSTALL_DIR = $Tools
    $env:UV_NO_MODIFY_PATH = "1"
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
}
Step (T 'step_python')
Push-Location (Join-Path $AppDir "backend")
try {
    & $uv sync --frozen --no-dev --python 3.12 --quiet
    if ($LASTEXITCODE -ne 0) { Fail (T 'fail_uv_sync') }
} finally { Pop-Location }

$nodeDir = $null
$systemNode = Get-Command node -ErrorAction SilentlyContinue
if ($systemNode -and [int](& node -p "process.versions.node.split('.')[0]") -ge $NodeMajor) {
    $nodeDir = Split-Path $systemNode.Source
} else {
    $nodeDir = Join-Path $Tools "node"
    if (-not (Test-Path (Join-Path $nodeDir "node.exe"))) {
        Step (T 'step_node' $NodeMajor)
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
Step (T 'step_build')
$env:Path = "$nodeDir;$env:Path"
Push-Location (Join-Path $AppDir "frontend")
try {
    & (Join-Path $nodeDir "npm.cmd") ci --no-audit --no-fund --silent
    if ($LASTEXITCODE -ne 0) { Fail (T 'fail_npm_ci') }
    & (Join-Path $nodeDir "npm.cmd") run build --silent | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail (T 'fail_build') }
} finally { Pop-Location }

$meiliExe = ""
if ($WithSearch) {
    $meiliExe = Join-Path $Tools "meilisearch-$MeiliVersion.exe"
    if (-not (Test-Path $meiliExe)) {
        Step (T 'step_meili' $MeiliVersion)
        Invoke-WebRequest -UseBasicParsing -OutFile $meiliExe `
            -Uri "https://github.com/meilisearch/meilisearch/releases/download/$MeiliVersion/meilisearch-windows-amd64.exe"
    }
}

# --- 3./4. Settings + database -------------------------------------------------------------------
if (-not (Test-Path $EnvFile)) {
    Step (T 'step_settings' $EnvFile)
    $dbPassword = New-Secret 32
    # Settings template in the installation language (homedms.env.<language>.example), English as the fallback.
    # Read as UTF-8: Get-Content would read it as ANSI in Windows PowerShell 5.1 and spoil umlauts / Cyrillic.
    $template = Join-Path $AppDir "homedms.env.$(Get-InstallerLanguage $Language).example"
    if (-not (Test-Path $template)) { $template = Join-Path $AppDir "homedms.env.example" }
    $text = [IO.File]::ReadAllText($template, [Text.Encoding]::UTF8)
    $values = @{
        "DATABASE_URL"     = "postgresql://homedms:$dbPassword@127.0.0.1:5432/homedms"
        "OLLAMA_URL"       = "http://127.0.0.1:11434"
        "JWT_SECRET"       = New-Secret 64
        "MEILISEARCH_KEY"  = New-Secret 40
        "DOCUMENTS_PATH"   = Slash (Join-Path $DataFolder "documents")
        "SCAN_PATH"        = Slash (Join-Path $DataFolder "scan")
        "LOG_DIR"          = Slash (Join-Path $DataFolder "logs")
        "MEILISEARCH_DATA" = Slash (Join-Path $DataFolder "meilisearch")
        "TESSERACT_CMD"    = Slash $tesseract
        "PORT"             = "$Port"
        "HTTPS_PORT"       = "$HttpsPort"
        "TLS_DIR"          = Slash (Join-Path $DataFolder "tls")
        "TESSDATA_DIR"     = Slash (Join-Path $DataFolder "tessdata")
        "SETUP_CODE"       = ((New-Secret 12) -replace '(.{4})(?!$)', '$1-').ToUpper()
    }
    foreach ($key in $values.Keys) { $text = [regex]::Replace($text, "(?m)^$key=.*$", "$key=$($values[$key])") }
    Write-Utf8 $EnvFile $text
} else {
    $dbPassword = ([regex]::Match((Get-Content $EnvFile -Raw), "(?m)^DATABASE_URL=postgresql://[^:]*:([^@]*)@")).Groups[1].Value
}
# Switch the search on or off according to the option
$text = Get-Content $EnvFile -Raw
if ($WithSearch) {
    $text = [regex]::Replace($text, "(?m)^MEILISEARCH_BINARY=.*$", "MEILISEARCH_BINARY=$(Slash $meiliExe)")
    $text = [regex]::Replace($text, "(?m)^MEILISEARCH_URL=[ \t\r]*$", "MEILISEARCH_URL=http://127.0.0.1:7700")
} else {
    $text = [regex]::Replace($text, "(?m)^MEILISEARCH_BINARY=.*$", "MEILISEARCH_BINARY=")
    $text = [regex]::Replace($text, "(?m)^MEILISEARCH_URL=.*$", "MEILISEARCH_URL=")
}
Write-Utf8 $EnvFile $text
icacls $EnvFile /inheritance:r /grant:r "*S-1-5-32-544:F" "*S-1-5-18:F" | Out-Null   # administrators + SYSTEM only

Step (T 'step_database')
$env:PGPASSWORD = $superPassword
function Invoke-Psql([string]$Sql, [string]$Database = "postgres") {
    $out = & $psql -U postgres -h 127.0.0.1 -d $Database -tAc $Sql
    if ($LASTEXITCODE -ne 0) { Fail (T 'fail_psql') }
    return $out
}
if ((Invoke-Psql "SELECT 1 FROM pg_roles WHERE rolname='homedms'") -ne "1") {
    Invoke-Psql "CREATE ROLE homedms LOGIN PASSWORD '$dbPassword'" | Out-Null
}
if ((Invoke-Psql "SELECT 1 FROM pg_database WHERE datname='homedms'") -ne "1") {
    Invoke-Psql "CREATE DATABASE homedms OWNER homedms ENCODING 'UTF8' TEMPLATE template0" | Out-Null
}
Invoke-Psql "SET client_min_messages = warning; CREATE EXTENSION IF NOT EXISTS pg_trgm" "homedms" | Out-Null   # no "already exists" notice
Remove-Item Env:PGPASSWORD

# --- 5. Autostart + 6. Firewall ------------------------------------------------------------------
Step (T 'step_autostart' $TaskName)
$python = Join-Path $AppDir "backend\.venv\Scripts\python.exe"
$action = New-ScheduledTaskAction -Execute $python -Argument "-m homedms.server" -WorkingDirectory (Join-Path $AppDir "backend")
$trigger = New-ScheduledTaskTrigger -AtStartup
$principalTask = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Unregister-ScheduledTask -TaskName "HomeDMS" -Confirm:$false -ErrorAction SilentlyContinue   # former name
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principalTask -Settings $settings `
    -Description (T 'task_description') -Force | Out-Null
# End leftovers of an earlier start, then start again
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like "*homedms.*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-ScheduledTask -TaskName $TaskName

Step (T 'step_firewall' $Port $HttpsPort)
# netsh instead of Get-/New-NetFirewallRule: on PCs with many rules (about 2000 is normal) the cmdlets take
# minutes or hang, netsh answers in a fraction of a second.
foreach ($ruleName in "Famulus DMS", "HomeDMS") {   # "HomeDMS" = former name
    & netsh advfirewall firewall delete rule name="$ruleName" 2>&1 | Out-Null   # exit code 1 = there was none
}
& netsh advfirewall firewall add rule name="Famulus DMS" dir=in action=allow protocol=TCP "localport=$Port,$HttpsPort" profile=private,domain | Out-Null
if ($LASTEXITCODE -ne 0) {
    Warn (T 'warn_firewall' $Port $HttpsPort)
}

# Deliberately 127.0.0.1 instead of "localhost": the server listens on IPv4, but "localhost" is resolved to IPv6
# (::1) first - on some PCs (e.g. with Docker Desktop/WSL) that runs into a timeout instead of an immediate
# error, and the check fails although Famulus DMS works in the browser.
$ok = $false
for ($i = 0; $i -lt 90; $i++) {
    try { Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2 | Out-Null; $ok = $true; break } catch { Start-Sleep -Seconds 1 }
}
# Only a warning: the remaining steps (certificate, setup code, browser) should run anyway
if (-not $ok) { Warn (T 'warn_no_response' $Port (Join-Path $DataFolder 'logs\homedms.log')) }

# Trust the certificate authority on this PC right away (other devices: page /zertifikat)
$caFile = Join-Path $DataFolder "tls\ca.crt"
if (Test-Path $caFile) {
    Import-Certificate -FilePath $caFile -CertStoreLocation Cert:\LocalMachine\Root | Out-Null
    Write-Host (T 'info_cert')
}
$ip = Get-LanAddress
if (-not $ip) { $ip = $env:COMPUTERNAME }
Step (T 'step_done' $HttpsPort $ip)
Write-Host (T 'info_devices' $ip $Port)
$setupCode = ([regex]::Match((Get-Content $EnvFile -Raw), "(?m)^SETUP_CODE=(\S+)")).Groups[1].Value
Write-Host (T 'info_wizard')
if ($setupCode) { Write-Host (T 'info_code' $setupCode) -ForegroundColor Green }
Write-Host (T 'info_paths' (Join-Path $DataFolder 'documents') (Join-Path $DataFolder 'scan'))
Write-Host (T 'info_logs' (Join-Path $DataFolder 'logs') $TaskName)
if (-not $NoAI) { Write-Host (T 'info_ollama_note') }
Start-Process "https://localhost:$HttpsPort"
