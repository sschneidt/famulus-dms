<#
.SYNOPSIS
  Remove Famulus DMS from a Windows PC (Russian).

.DESCRIPTION
  Open PowerShell AS ADMINISTRATOR, change to the Famulus DMS folder and run:

    powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-windows.ru.ps1

  Options (English names): -DryRun (only list the steps, change nothing, no administrator needed)   -Yes   -DataFolder D:\Famulus-Data
  The uninstallation runs in Russian. This script only selects the language;
  the work is done by uninstall-windows.ps1 (see its help).
#>
[CmdletBinding()]
param(
    [string]$DataFolder = "",
    [switch]$DryRun,
    [switch]$Yes
)

$options = @{
    Language   = "ru"
    DataFolder = $DataFolder
    DryRun     = [bool]$DryRun
    Yes        = [bool]$Yes
}
& (Join-Path $PSScriptRoot "uninstall-windows.ps1") @options
