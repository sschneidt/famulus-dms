@echo off
rem Startet den Famulus-DMS-Smoke-Test - umgeht die PowerShell-Ausfuehrungsrichtlinie nur fuer diesen Aufruf.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0smoke-test.ps1" %*
