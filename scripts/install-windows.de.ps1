<#
.SYNOPSIS
  Famulus DMS auf einem Windows-PC installieren (Deutsch). Ohne Docker und ohne NAS.

.DESCRIPTION
  PowerShell ALS ADMINISTRATOR oeffnen, in den Famulus-DMS-Ordner wechseln und starten:

    powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.de.ps1

  Optionen: -DatenOrdner D:\Famulus-Data   -Port 8000   -HttpsPort 8443   -OhneKI   -MitSuche
  Dieses Skript waehlt nur die Sprache; die Installation selbst steckt in install-windows.ps1.
#>
[CmdletBinding()]
param(
    [string]$DatenOrdner = "",
    [int]$Port = 8000,
    [int]$HttpsPort = 8443,
    [switch]$OhneKI,
    [switch]$MitSuche
)

$options = @{
    Language   = "de"
    DataFolder = $DatenOrdner
    Port       = $Port
    HttpsPort  = $HttpsPort
    NoAI       = [bool]$OhneKI
    WithSearch = [bool]$MitSuche
}
& (Join-Path $PSScriptRoot "install-windows.ps1") @options
