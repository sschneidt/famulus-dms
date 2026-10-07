@echo off
rem Update Famulus DMS (Docker) - Russian. Options: -BackupOnly, -NoBackup
rem Bypasses the PowerShell execution policy for this one call only.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1" -Language ru %*
