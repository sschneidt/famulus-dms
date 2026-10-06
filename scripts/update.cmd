@echo off
rem Aktualisiert Famulus DMS (Docker) - umgeht die PowerShell-Ausfuehrungsrichtlinie nur fuer diesen Aufruf.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1" %*
