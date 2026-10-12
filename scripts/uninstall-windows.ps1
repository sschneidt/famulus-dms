<#
.SYNOPSIS
  Remove Famulus DMS from a Windows PC (the installation made by install-windows.ps1).

.DESCRIPTION
  Open PowerShell AS ADMINISTRATOR, change to the Famulus DMS folder and run ONE of these:

    powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-windows.ps1      language chosen automatically
    powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-windows.en.ps1   English
    powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-windows.de.ps1   Deutsch
    powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-windows.ru.ps1   Russian

  The script first looks at what is installed, then asks what to remove, shows the plan and asks once more.
  Only then it changes anything. Destructive steps are never answered automatically:

    1. Stop Famulus DMS, remove the autostart task, the firewall rule and the certificate  (always asked first)
    2. Delete the program files in the Famulus DMS folder (settings, tools, Python, web interface). The source
       code stays, the files can be created again.
    3. Delete the database "homedms" and its user from PostgreSQL
    4. Delete the DATA FOLDER with all documents - you must type a confirmation word. Before steps 3 and 4 the
       script offers a backup (documents, scan folder, certificates, database dump).
    5. Uninstall PostgreSQL, Tesseract and Ollama via winget (each asked separately - only if nothing else
       uses them) and delete their leftovers

  A Docker setup of Famulus DMS and the source code are never touched.

  Options:
    -DryRun                     only list what would happen, change nothing (works without administrator rights)
    -Yes                        answer the harmless questions (steps 1 and 2 and the final confirmation) with yes;
                                together with -DryRun it answers all questions, to show the complete plan
    -DataFolder D:\Famulus-Data name the data folder if homedms.env cannot be read   (German alias: -DatenOrdner)
    -Language auto|de|en|ru     language (default: Windows display language, English if there is no translation)

  The texts live in scripts\lang\uninstall-windows.<language>.msg.
#>
[CmdletBinding()]
param(
    [Alias("DatenOrdner")][string]$DataFolder = "",
    [Alias("Testlauf")][switch]$DryRun,
    [Alias("Ja")][switch]$Yes,
    [ValidateSet("auto", "de", "en", "ru")][string]$Language = "auto"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }   # show umlauts / Cyrillic correctly

$AppDir = Split-Path -Parent $PSScriptRoot
$Tools = Join-Path $AppDir ".tools"
$EnvFile = Join-Path $AppDir "homedms.env"
$TaskNames = "Famulus DMS", "HomeDMS"       # "HomeDMS" = former name
$FirewallNames = "Famulus DMS", "HomeDMS"
$Programs = @(
    @{ Id = "PostgreSQL.PostgreSQL.16"; Name = "PostgreSQL 16" },
    @{ Id = "UB-Mannheim.TesseractOCR"; Name = "Tesseract" },
    @{ Id = "Ollama.Ollama"; Name = "Ollama" }
)

# --- Messages (scripts\lang\uninstall-windows.<language>.msg; same loader as install-windows.ps1) ----------
function Import-Messages([string]$Code) {
    $messages = @{}
    $file = Join-Path (Join-Path $PSScriptRoot "lang") "uninstall-windows.$Code.msg"
    if (Test-Path $file) {
        foreach ($line in [IO.File]::ReadAllLines($file, [Text.Encoding]::UTF8)) {
            if ($line -match "^\s*(\w+)\s*=\s*'((?:[^']|'')*)'\s*$") { $messages[$Matches[1]] = $Matches[2].Replace("''", "'") }
        }
    }
    return $messages
}
function Get-UninstallLanguage([string]$Requested) {
    if ($Requested -ne "auto") { return $Requested }
    $code = (Get-UICulture).TwoLetterISOLanguageName
    if ($code -in "de", "ru") { return $code }
    return "en"
}
$Messages = Import-Messages (Get-UninstallLanguage $Language)
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

function Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Warn($text) { Write-Host "!! $text" -ForegroundColor Yellow }
function Fail($text) { Write-Host ((T 'label_error') + " $text") -ForegroundColor Red; exit 1 }

# --- Helpers ---------------------------------------------------------------------------------------
# Native programs may write to stderr (e.g. "access denied"). With $ErrorActionPreference = "Stop" Windows
# PowerShell 5.1 turns that into a terminating error - so they run with "Continue" and callers look at
# $LASTEXITCODE instead.
function Invoke-Native([scriptblock]$Command) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { return (& $Command 2>&1) } finally { $ErrorActionPreference = $previous }
}
function Find-First([string[]]$patterns) {
    foreach ($p in $patterns) {
        $hit = Get-ChildItem -Path $p -ErrorAction SilentlyContinue | Sort-Object FullName -Descending | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    return $null
}
function Get-FolderInfo([string]$Path) {
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return @{ Files = 0; MB = 0 } }
    $items = Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue
    $bytes = ($items | Measure-Object Length -Sum).Sum
    return @{ Files = @($items).Count; MB = [math]::Round([double]$bytes / 1MB, 1) }
}
# A folder is only deleted if it looks like a Famulus DMS data folder - never a drive, a system folder or
# the program folder
function Test-DataFolderSafe([string]$Path) {
    if (-not $Path) { return $false }
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    if ($full.Length -le 3) { return $false }
    $app = $script:AppDir.TrimEnd('\')
    if ($full -ieq $app -or $app.StartsWith($full + '\', [StringComparison]::OrdinalIgnoreCase)) { return $false }
    foreach ($system in $env:SystemRoot, $env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:USERPROFILE, $env:SystemDrive) {
        if ($system -and $full -ieq $system.TrimEnd('\')) { return $false }
    }
    return ((Test-Path -LiteralPath (Join-Path $full 'documents')) -and (Test-Path -LiteralPath (Join-Path $full 'tls')))
}
function Test-ScheduledTaskExists([string]$Name) { Invoke-Native { schtasks /query /tn $Name } | Out-Null; return ($LASTEXITCODE -eq 0) }
function Test-FirewallRuleExists([string]$Name) { Invoke-Native { netsh advfirewall firewall show rule name="$Name" } | Out-Null; return ($LASTEXITCODE -eq 0) }
function Test-WingetPackage([string]$Id) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { return $false }
    return ((Invoke-Native { winget list --id $Id --exact } | Out-String) -match [regex]::Escape($Id))
}
# The certificate store is read through .NET: the Cert: drive does not exist when Windows PowerShell was started
# from PowerShell 7 (inherited module path) - the certificate would silently not be found.
function Open-RootStore([bool]$Writable, [string]$Name = "Root", [string]$Location = "LocalMachine") {
    $store = New-Object Security.Cryptography.X509Certificates.X509Store($Name, $Location)
    $store.Open($(if ($Writable) { "ReadWrite" } else { "ReadOnly" }))
    return $store
}
function Get-CaThumbprint {
    $own = $null
    $caFile = if ($script:DataFolder) { Join-Path $script:DataFolder "tls\ca.crt" } else { $null }
    if ($caFile -and (Test-Path -LiteralPath $caFile)) {
        try { $own = (New-Object Security.Cryptography.X509Certificates.X509Certificate2 $caFile).Thumbprint } catch { }
    }
    $found = @()
    $store = Open-RootStore $false
    try {
        foreach ($c in $store.Certificates) {
            # the certificate of this installation, or (data folder unknown) any CA made by Famulus DMS / HomeDMS
            if ($c.Thumbprint -eq $own -or ($c.Subject -match 'lokale Zertifizierungsstelle' -and $c.Subject -match 'O=(HomeDMS|Famulus)')) { $found += $c.Thumbprint }
        }
    } finally { $store.Close() }
    return @($found | Sort-Object -Unique)
}
function Remove-RootCertificate([string]$Thumbprint, [string]$Name = "Root", [string]$Location = "LocalMachine") {   # Name/Location: for tests
    $store = Open-RootStore $true $Name $Location
    try { foreach ($c in @($store.Certificates | Where-Object { $_.Thumbprint -eq $Thumbprint })) { $store.Remove($c) } }
    finally { $store.Close() }
}
function Get-PostgresPassword {
    foreach ($name in "postgres-admin-password.txt", "postgres-admin-passwort.txt") {   # the second is the name used before the rename
        $file = if ($script:DataFolder) { Join-Path $script:DataFolder $name } else { $null }
        if ($file -and (Test-Path -LiteralPath $file)) { try { return (Get-Content -LiteralPath $file -Raw -ErrorAction Stop).Trim() } catch { } }
    }
    return $null
}
function Invoke-Psql([string]$Sql, [string]$Database = "postgres") {
    return (Invoke-Native { & $script:Psql -U postgres -h 127.0.0.1 -d $Database -tAc $Sql })
}

function Test-YesAnswer([string]$Answer) { return (((T 'answer_yes') -split ',') -contains $Answer.Trim().ToLower()) }
# $Safe = may be answered by -Yes. In a dry run -Yes answers everything (nothing is changed anyway).
function Ask([string]$Question, [bool]$Safe = $false) {
    if ($DryRun -and $Yes) { Write-Host "$Question $(T 'info_dry_yes')"; return $true }
    if ($Safe -and $Yes) { Write-Host "$Question $(T 'info_auto_yes')"; return $true }
    if ([Console]::IsInputRedirected) { return $false }
    return (Test-YesAnswer (Read-Host "$Question $(T 'yes_no_hint')"))
}
function Confirm-Word([string]$Word) {
    if ($DryRun -and $Yes) { return $true }
    if ([Console]::IsInputRedirected) { return $false }
    $answer = (Read-Host (T 'ask_data_confirm' $Word)).Trim()
    return ($answer -ieq $Word -or $answer -ieq "DELETE")
}
# Everything that changes something goes through here: a dry run only says that it would have
function Invoke-Change([scriptblock]$Action, [string[]]$Items = @()) {
    if ($DryRun) {
        foreach ($item in $Items) { Write-Host "   $item" }
        Write-Host (T 'info_dry_skipped')
        return
    }
    & $Action
}
function Remove-Path([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    try { Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop; Write-Host (T 'info_removed' $Path) }
    catch { Warn (T 'warn_delete_failed' $Path $_.Exception.Message) }
}

# --- Prerequisites ---------------------------------------------------------------------------------
$isAdmin = (New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($DryRun) { Write-Host (T 'banner_dry_run') -ForegroundColor Magenta }
if (-not $isAdmin -and -not $DryRun) { Fail (T 'fail_admin') }
if (-not (Test-Path (Join-Path $AppDir "backend\pyproject.toml"))) { Fail (T 'fail_appdir' $AppDir) }

# --- 1. Look at what is installed ------------------------------------------------------------------
Step (T 'step_scan')
$dataKnown = [bool]$DataFolder
if (-not $DataFolder -and (Test-Path $EnvFile)) {
    try {
        $docs = [regex]::Match((Get-Content $EnvFile -Raw -ErrorAction Stop), "(?m)^DOCUMENTS_PATH=(\S+)").Groups[1].Value
        if ($docs) { $DataFolder = Split-Path ($docs -replace '/', '\') -Parent }
    } catch { }
}
$dataSafe = Test-DataFolderSafe $DataFolder
$dataInfo = if ($dataSafe) { Get-FolderInfo $DataFolder } else { @{ Files = 0; MB = 0 } }

$wordYes = T 'word_present'; $wordNo = T 'word_absent'; $wordUnknown = T 'word_unknown'
$taskFound = $false; foreach ($n in $TaskNames) { if (Test-ScheduledTaskExists $n) { $taskFound = $true } }
$taskShown = if ($taskFound) { $wordYes } elseif ($isAdmin) { $wordNo } else { $wordUnknown }   # tasks of SYSTEM are invisible without administrator rights
$firewallFound = $false; foreach ($n in $FirewallNames) { if (Test-FirewallRuleExists $n) { $firewallFound = $true } }
$certs = @(Get-CaThumbprint)
$filesToDelete = @($EnvFile, $Tools, (Join-Path $AppDir "backend\.venv"), (Join-Path $AppDir "frontend\node_modules"), (Join-Path $AppDir "frontend\dist")) | Where-Object { Test-Path -LiteralPath $_ }

$Psql = Find-First @("$env:ProgramFiles\PostgreSQL\*\bin\psql.exe")
$pgPassword = Get-PostgresPassword
$databaseState = $wordUnknown
$databaseExists = $false
if ($Psql -and $pgPassword) {
    $env:PGPASSWORD = $pgPassword
    $answer = Invoke-Psql "SELECT 1 FROM pg_database WHERE datname='homedms'"
    $env:PGPASSWORD = $null
    if ($LASTEXITCODE -eq 0) { $databaseExists = ("$answer".Trim() -eq "1"); $databaseState = if ($databaseExists) { $wordYes } else { $wordNo } }
}

Write-Host (T 'info_found')
Write-Host (T 'item_task' $TaskNames[0] $taskShown)
Write-Host (T 'item_firewall' $FirewallNames[0] $(if ($firewallFound) { $wordYes } else { $wordNo }))
Write-Host (T 'item_cert' $(if ($certs.Count) { $wordYes } else { $wordNo }))
Write-Host (T 'item_files' $AppDir $(if ($filesToDelete.Count) { $wordYes } else { $wordNo }))
if ($dataSafe) { Write-Host (T 'item_data' $DataFolder ("{0} / {1} MB" -f $dataInfo.Files, $dataInfo.MB)) }
elseif ($DataFolder) { Warn (T 'info_data_unsafe' $DataFolder) }
else { Warn (T 'info_data_unknown') }
Write-Host (T 'item_database' $databaseState)
$programsFound = @()
foreach ($p in $Programs) {
    $present = Test-WingetPackage $p.Id
    if ($present) { $programsFound += $p }
    Write-Host (T 'item_program' $p.Name $(if ($present) { $wordYes } else { $wordNo }))
}

# --- 2. Ask what to remove (nothing is changed yet) --------------------------------------------------
Write-Host ""
$doApp = Ask (T 'ask_app') $true
if (-not $doApp) {
    if ([Console]::IsInputRedirected -and -not $Yes) { Write-Host (T 'info_no_input') }
    Write-Host (T 'info_cancelled'); exit 0
}
$doFiles = $false; $doDatabase = $false; $doData = $false; $doBackup = $false; $backupFolder = $null
$doPrograms = @(); $doLeftovers = @()
if ($filesToDelete.Count) { $doFiles = Ask (T 'ask_files' $AppDir) $true }
if ($Psql -and ($databaseExists -or $databaseState -eq $wordUnknown)) { $doDatabase = Ask (T 'ask_database') }
if ($dataSafe) {
    $doData = (Ask (T 'ask_data' $DataFolder $dataInfo.Files $dataInfo.MB)) -and (Confirm-Word (T 'word_delete'))
}
if ($doDatabase -or $doData) {
    $doBackup = Ask (T 'ask_backup')
    if ($doBackup) {
        $backupFolder = if ($DryRun -and $Yes) { Join-Path $env:USERPROFILE "Famulus-DMS-Backup" } else { (Read-Host (T 'prompt_backup_folder')).Trim().Trim('"') }
        if (-not $backupFolder -or -not [IO.Path]::IsPathRooted($backupFolder)) { Fail (T 'fail_backup_folder' $backupFolder) }
    }
}
foreach ($p in $programsFound) { if (Ask (T 'ask_program' $p.Name)) { $doPrograms += $p } }
$pgDir = Join-Path $env:ProgramFiles "PostgreSQL"
$ollamaDir = Join-Path $env:USERPROFILE ".ollama"
foreach ($pair in @(@("PostgreSQL.PostgreSQL.16", $pgDir), @("Ollama.Ollama", $ollamaDir))) {
    if (($doPrograms | Where-Object { $_.Id -eq $pair[0] }) -and (Test-Path -LiteralPath $pair[1])) {
        if (Ask (T 'ask_leftovers' $pair[1] (Get-FolderInfo $pair[1]).MB)) { $doLeftovers += $pair[1] }
    }
}

# --- 3. Show the plan and ask once more -----------------------------------------------------------
Write-Host ""
Write-Host (T 'plan_header')
Write-Host (T 'plan_app')
if ($doBackup) { Write-Host (T 'plan_backup' $backupFolder) }
if ($doDatabase) { Write-Host (T 'plan_database') }
if ($doFiles) { Write-Host (T 'plan_files' $AppDir) }
if ($doData) { Write-Host (T 'plan_data' $DataFolder) }
foreach ($p in $doPrograms) { Write-Host (T 'plan_program' $p.Name) }
foreach ($d in $doLeftovers) { Write-Host (T 'plan_leftovers' $d) }
Write-Host ""
if (-not (Ask (T 'ask_proceed') $true)) { Write-Host (T 'info_cancelled'); exit 0 }

# --- 4. Carry out ---------------------------------------------------------------------------------
Step (T 'step_stop')
Invoke-Change {
    foreach ($n in $TaskNames) { Invoke-Native { schtasks /end /tn $n } | Out-Null }
    # processes started from this program folder (the Python of the installation, Meilisearch)
    Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$AppDir\*" } | Stop-Process -Force -ErrorAction SilentlyContinue
}

if ($doBackup) {
    Step (T 'step_backup' $backupFolder)
    Invoke-Change {
        try {
            $target = Join-Path $backupFolder ("famulus-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
            New-Item -ItemType Directory -Force -Path $target | Out-Null
            if ($dataSafe) {
                foreach ($sub in "documents", "scan", "tls") {
                    if (Test-Path -LiteralPath (Join-Path $DataFolder $sub)) { Copy-Item -LiteralPath (Join-Path $DataFolder $sub) -Destination (Join-Path $target $sub) -Recurse -ErrorAction Stop }
                }
            }
            if ($Psql) {
                if (-not $pgPassword) {
                    $secure = Read-Host (T 'prompt_postgres_password') -AsSecureString
                    $script:pgPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
                }
                $env:PGPASSWORD = $pgPassword
                $pgDump = Join-Path (Split-Path $Psql) "pg_dump.exe"
                Invoke-Native { & $pgDump -U postgres -h 127.0.0.1 -Fc homedms -f (Join-Path $target "homedms.dump") } | Out-Null
                $dumpOk = ($LASTEXITCODE -eq 0)
                $env:PGPASSWORD = $null
                if (-not $dumpOk) { throw "pg_dump" }
            }
            Write-Host (T 'info_backup_done' $target)
        } catch {
            foreach ($n in $TaskNames) { Invoke-Native { schtasks /run /tn $n } | Out-Null }   # leave the app as it was
            Fail (T 'fail_backup' $_.Exception.Message)
        }
    }
}

Step (T 'step_autostart')
Invoke-Change { foreach ($n in $TaskNames) { Invoke-Native { schtasks /delete /tn $n /f } | Out-Null } } $TaskNames

Step (T 'step_firewall')
Invoke-Change { foreach ($n in $FirewallNames) { Invoke-Native { netsh advfirewall firewall delete rule name="$n" } | Out-Null } } $FirewallNames

Step (T 'step_cert')
Invoke-Change { foreach ($t in $certs) { Remove-RootCertificate $t; Write-Host (T 'info_removed' $t) } } $certs

if ($doDatabase) {
    Step (T 'step_database')
    Invoke-Change {
        $ok = $false
        try {
            Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue | Where-Object Status -ne Running | Start-Service
            if (-not $pgPassword) {
                $secure = Read-Host (T 'prompt_postgres_password') -AsSecureString
                $script:pgPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
            }
            $env:PGPASSWORD = $pgPassword
            Invoke-Psql "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='homedms'" | Out-Null
            Invoke-Psql "DROP DATABASE IF EXISTS homedms" | Out-Null
            $ok = ($LASTEXITCODE -eq 0)
            if ($ok) { Invoke-Psql "DROP ROLE IF EXISTS homedms" | Out-Null; $ok = ($LASTEXITCODE -eq 0) }
        } catch { $ok = $false }
        $env:PGPASSWORD = $null
        if (-not $ok) { Warn (T 'warn_database') }
    }
}

if ($doFiles) {
    Step (T 'step_files')
    Invoke-Change { foreach ($p in $filesToDelete) { Remove-Path $p } } $filesToDelete
}

if ($doData) {
    Step (T 'step_data')
    Invoke-Change { if (Test-DataFolderSafe $DataFolder) { Remove-Path $DataFolder } } @($DataFolder)
}

if ($doPrograms.Count) {
    Step (T 'step_programs')
    foreach ($p in $doPrograms) {
        Invoke-Change {
            Invoke-Native { winget uninstall --id $p.Id --exact --silent } | ForEach-Object { Write-Host "$_" }
            # -1978335212 = nothing installed under this id - not an error
            if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne -1978335212) { Warn (T 'warn_program' $p.Name $LASTEXITCODE) }
        } @($p.Name)
    }
}

if ($doLeftovers.Count) {
    Step (T 'step_leftovers')
    Invoke-Change { foreach ($d in $doLeftovers) { Remove-Path $d } } $doLeftovers
}

Write-Host ""
Write-Host (T 'info_done') -ForegroundColor Green
Write-Host (T 'info_docker')
if ($certs.Count) { Write-Host (T 'info_phones') }
