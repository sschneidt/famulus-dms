@echo off
rem Startet den HomeDMS-Smoke-Test - umgeht die PowerShell-Ausfuehrungsrichtlinie nur fuer diesen Aufruf.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0smoke-test.ps1" %*
