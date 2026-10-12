<#
.SYNOPSIS
  Remove Famulus DMS from a Windows PC (English).

.DESCRIPTION
  Open PowerShell AS ADMINISTRATOR, change to the Famulus DMS folder and run:

    powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-windows.en.ps1

  Options: -DryRun (only list the steps, change nothing, no administrator needed)   -Yes   -DataFolder D:\Famulus-Data
  This script only selects the language; the work is done by uninstall-windows.ps1 (see its help).
#>
[CmdletBinding()]
param(
    [string]$DataFolder = "",
    [switch]$DryRun,
    [switch]$Yes
)

$options = @{
    Language   = "en"
    DataFolder = $DataFolder
    DryRun     = [bool]$DryRun
    Yes        = [bool]$Yes
}
& (Join-Path $PSScriptRoot "uninstall-windows.ps1") @options
