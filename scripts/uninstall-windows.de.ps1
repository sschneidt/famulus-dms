<#
.SYNOPSIS
  Famulus DMS von einem Windows-PC entfernen (Deutsch).

.DESCRIPTION
  PowerShell ALS ADMINISTRATOR oeffnen, in den Famulus-DMS-Ordner wechseln und starten:

    powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-windows.de.ps1

  Optionen: -Testlauf (Schritte nur auflisten, nichts aendern, kein Administrator noetig)   -Ja   -DatenOrdner D:\Famulus-Data
  Dieses Skript waehlt nur die Sprache; die Arbeit macht uninstall-windows.ps1 (siehe dessen Hilfe).
#>
[CmdletBinding()]
param(
    [string]$DatenOrdner = "",
    [switch]$Testlauf,
    [switch]$Ja
)

$options = @{
    Language   = "de"
    DataFolder = $DatenOrdner
    DryRun     = [bool]$Testlauf
    Yes        = [bool]$Ja
}
& (Join-Path $PSScriptRoot "uninstall-windows.ps1") @options
