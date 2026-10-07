@echo off
rem Famulus DMS aktualisieren (Docker) - Deutsch. Optionen: -BackupOnly (oder -NurSichern), -NoBackup (oder -OhneSicherung)
rem Umgeht die PowerShell-Ausfuehrungsrichtlinie nur fuer diesen Aufruf.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1" -Language de %*
