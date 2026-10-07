<#
.SYNOPSIS
  Install Famulus DMS on a Windows PC (English). Without Docker and without a NAS.

.DESCRIPTION
  Open PowerShell AS ADMINISTRATOR, change to the Famulus DMS folder and run:

    powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.en.ps1

  Options: -DataFolder D:\Famulus-Data   -Port 8000   -HttpsPort 8443   -NoAI   -WithSearch
  This script only selects the language; the installation itself is install-windows.ps1.
#>
[CmdletBinding()]
param(
    [string]$DataFolder = "",
    [int]$Port = 8000,
    [int]$HttpsPort = 8443,
    [switch]$NoAI,
    [switch]$WithSearch
)

$options = @{
    Language   = "en"
    DataFolder = $DataFolder
    Port       = $Port
    HttpsPort  = $HttpsPort
    NoAI       = [bool]$NoAI
    WithSearch = [bool]$WithSearch
}
& (Join-Path $PSScriptRoot "install-windows.ps1") @options
