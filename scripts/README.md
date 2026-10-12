# Skripte

| Skript | Für | Was es tut |
|---|---|---|
| [`install-windows.de.ps1`](install-windows.de.ps1), [`.en.ps1`](install-windows.en.ps1), [`.ru.ps1`](install-windows.ru.ps1) | Windows-PC **ohne Docker** | Installiert PostgreSQL, Tesseract, Ollama und die App, richtet Autostart (geplante Aufgabe „Famulus DMS“) und Firewall ein. **Je Sprache ein Skript** (Deutsch, English, Русский): Die Installation läuft in dieser Sprache. Fragt beim ersten Lauf nach dem Datenordner (Vorschlag `C:\Famulus-Data`). Als **Administrator** starten. |
| [`install-windows.ps1`](install-windows.ps1) | dasselbe | Die eigentliche Installation. Wählt die Sprache nach der Windows-Anzeigesprache oder per `-Language de\|en\|ru`. Die Texte stehen in [`lang/`](lang/). |
| [`uninstall-windows.de.ps1`](uninstall-windows.de.ps1), [`.en.ps1`](uninstall-windows.en.ps1), [`.ru.ps1`](uninstall-windows.ru.ps1) | Windows-PC (Installation **ohne Docker**) | Entfernt Famulus DMS wieder. Fragt Schritt für Schritt (Autostart/Firewall/Zertifikat, Programmdateien, Datenbank, **Datenordner mit allen Dokumenten**, PostgreSQL/Tesseract/Ollama), zeigt vorher einen Plan, bietet ein Backup an und löscht nichts Endgültiges ohne ausdrückliche Bestätigung. `-Testlauf` listet nur auf und ändert nichts. Als **Administrator** starten. |
| [`uninstall-windows.ps1`](uninstall-windows.ps1) | dasselbe | Die eigentliche Deinstallation (Sprache nach Windows-Anzeigesprache oder `-Language`). |
| [`install-linux.de.sh`](install-linux.de.sh), [`.en.sh`](install-linux.en.sh), [`.ru.sh`](install-linux.ru.sh) | Linux-Server **ohne Docker** | Dasselbe für Debian/Ubuntu mit systemd-Dienst `homedms`, **je Sprache ein Skript**. Datenordner über `HOMEDMS_DATA` (Standard `/var/lib/homedms`). Mit `sudo` starten. |
| [`install-linux.sh`](install-linux.sh) | dasselbe | Die eigentliche Installation. Sprache nach `LANG` oder per `--lang de\|en\|ru`. |
| [`update.de.cmd`](update.de.cmd), [`.en.cmd`](update.en.cmd), [`.ru.cmd`](update.ru.cmd) | Windows mit **Docker** | Sichert die Datenbank, holt die neue Version, startet neu und prüft den Start. **Je Sprache ein Skript.** |
| [`update.cmd`](update.cmd) / [`update.ps1`](update.ps1) | dasselbe | Das eigentliche Update (Sprache nach Windows-Anzeigesprache oder `-Language`). |
| [`update.de.sh`](update.de.sh), [`.en.sh`](update.en.sh), [`.ru.sh`](update.ru.sh) / [`update.sh`](update.sh) | Linux/NAS mit **Docker** | Wie oben (`update.sh` wählt die Sprache nach `LANG` oder `--lang`). |
| [`smoke-test.cmd`](smoke-test.cmd) / [`smoke-test.ps1`](smoke-test.ps1) | Entwickler, Docker | Ende-zu-Ende-Test des laufenden Stacks. **Legt Testdokumente an** (nach dem Lauf im Papierkorb) – nicht für einen Stack mit echten Daten gedacht. |
| [`testdaten/`](testdaten/) | Smoke-Test | Zwei Beispieldateien mit erfundenen Daten. |

## Aufrufe

```powershell
# Windows ohne Docker (PowerShell als Administrator, im Projektordner) - hier Deutsch;
# English: install-windows.en.ps1, Russian: install-windows.ru.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows.de.ps1
```

```powershell
# Windows ohne Docker wieder entfernen - zuerst ein Probelauf, der nur auflistet (auch ohne Administrator)
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-windows.de.ps1 -Testlauf
```

```powershell
# ... dann richtig (PowerShell als Administrator); English: uninstall-windows.en.ps1, Russian: uninstall-windows.ru.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-windows.de.ps1
```

```bash
# Linux ohne Docker (hier Deutsch; install-linux.en.sh / install-linux.ru.sh)
sudo bash scripts/install-linux.de.sh
```

```bash
# Update mit Docker (Linux/NAS) - Deutsch; update.en.sh / update.ru.sh
./scripts/update.de.sh
```

```powershell
# Update mit Docker (Windows) - Deutsch; update.en.cmd / update.ru.cmd
.\scripts\update.de.cmd
```

Die Installationsskripte (ohne Docker) und der Docker-Betrieb sind **getrennte Instanzen** mit eigener Datenbank.
Auf demselben Rechner nicht gleichzeitig betreiben: Docker vorher mit `docker compose stop` anhalten.

Optionen, Ablauf und Hintergründe: [Installation ohne Docker](../docs/Installation-ohne-Docker.md),
[Updates](../docs/Updates.md).

## Sprachen und Texte

Alle Meldungen der Installations- und Update-Skripte stehen in [`lang/`](lang/) – eine Datei je Skript und Sprache (`<Skript>.<Sprache>.msg`, ein Text je Zeile: `schluessel = 'Text'`). Die Skripte selbst sind englisch und reines ASCII. Eine neue Sprache braucht eine Katalogdatei je Skript und je ein Startskript. Der Test `backend/tests/test_installer_messages.py` prüft, dass kein Text in einer Sprache fehlt und die Platzhalter `{0}`, `{1}` überall gleich sind.
