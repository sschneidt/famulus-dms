@echo off
rem Update Famulus DMS (Docker) - language from the Windows display language.
rem Language scripts: update.de.cmd (Deutsch), update.en.cmd (English), update.ru.cmd (Russian).
rem Bypasses the PowerShell execution policy for this one call only.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update.ps1" %*
