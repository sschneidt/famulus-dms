# Skripte

| Skript | Für | Was es tut |
|---|---|---|
| [`install-windows.ps1`](install-windows.ps1) | Windows-PC **ohne Docker** | Installiert PostgreSQL, Tesseract, Ollama und die App, richtet Autostart (geplante Aufgabe „Famulus DMS“) und Firewall ein. Fragt beim ersten Lauf nach dem Datenordner (Vorschlag `C:\Famulus-Daten`). Als **Administrator** starten. |
| [`install-linux.sh`](install-linux.sh) | Linux-Server **ohne Docker** | Dasselbe für Debian/Ubuntu mit systemd-Dienst `homedms`. Datenordner über `HOMEDMS_DATA` (Standard `/var/lib/homedms`). Mit `sudo` starten. |
| [`update.cmd`](update.cmd) / [`update.ps1`](update.ps1) | Windows mit **Docker** | Sichert die Datenbank, holt die neue Version, startet neu und prüft den Start. |
| [`update.sh`](update.sh) | Linux/NAS mit **Docker** | Wie oben. |
| [`smoke-test.cmd`](smoke-test.cmd) / [`smoke-test.ps1`](smoke-test.ps1) | Entwickler, Docker | Ende-zu-Ende-Test des laufenden Stacks. **Legt Testdokumente an** (nach dem Lauf im Papierkorb) – nicht für einen Stack mit echten Daten gedacht. |
| [`testdaten/`](testdaten/) | Smoke-Test | Zwei Beispieldateien mit erfundenen Daten. |

## Aufrufe

```powershell
# Windows ohne Docker (PowerShell als Administrator, im Projektordner)
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.ps1
```

```bash
# Linux ohne Docker
sudo bash scripts/install-linux.sh
```

```bash
# Update mit Docker (Linux/NAS)
./scripts/update.sh
```

```powershell
# Update mit Docker (Windows)
.\scripts\update.cmd
```

Die Installationsskripte (ohne Docker) und der Docker-Betrieb sind **getrennte Instanzen** mit eigener Datenbank.
Auf demselben Rechner nicht gleichzeitig betreiben: Docker vorher mit `docker compose stop` anhalten.

Optionen, Ablauf und Hintergründe: [Installation ohne Docker](../docs/Installation-ohne-Docker.md),
[Updates](../docs/Updates.md).
