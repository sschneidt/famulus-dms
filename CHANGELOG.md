# Änderungsprotokoll – Famulus DMS

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach
[Semantic Versioning](https://semver.org/lang/de/): `MAJOR.MINOR.PATCH` – Fehlerkorrekturen
erhöhen die letzte Stelle, neue Funktionen die mittlere, unverträgliche Änderungen die erste.
Ablauf eines Releases und eines Updates: [docs/Updates.md](docs/Updates.md).

## [Unveröffentlicht]

### Neu
- Die Beispiel-Konfigurationen gibt es in drei Sprachen: `.env.example` (English), `.env.de.example`, `.env.ru.example` für Docker und `homedms.env.example`, `homedms.env.de.example`, `homedms.env.ru.example` für die Installation ohne Docker. Die Werte sind identisch, nur die Kommentare unterscheiden sich (ein Test erzwingt das). Die Installationsskripte nehmen die Vorlage passend zur Installationssprache; der Windows-Installer liest sie ausdrücklich als UTF-8. Die Platzhalter heißen jetzt überall `CHANGE_ME…`, die Adressen `127.0.0.1` statt `localhost`.
- Der Starter ohne Docker warnt jetzt auch, wenn `JWT_SECRET` noch der Platzhalter `CHANGE_ME…` aus der Vorlage ist.
- Deinstallationsskript für Windows (Installation ohne Docker): `uninstall-windows.de/.en/.ru.ps1` bzw. `uninstall-windows.ps1`. Es schaut, was installiert ist, fragt Schritt für Schritt, zeigt einen Plan und bietet vor dem Löschen ein Backup an. Datenbank, Datenordner mit allen Dokumenten und Programme werden nie automatisch entfernt; der Datenordner nur nach Eintippen eines Bestätigungswortes. `-Testlauf` listet alle Schritte auf, ohne etwas zu ändern.

## [0.2.0] – 2026-10-07

Erste Version unter dem Namen **Famulus DMS** (vorher „HomeDMS“) und die erste zur Veröffentlichung.

### Geändert
- Der Linux-Installer und die Update-Skripte laufen jetzt ebenfalls in mehreren Sprachen, je ein Skript für Deutsch, English
  und Русский: `install-linux.de/.en/.ru.sh`, `update.de/.en/.ru.sh` und `update.de/.en/.ru.cmd`. Die Hauptskripte
  (`install-linux.sh`, `update.sh`, `update.ps1`) sind englisch; die Texte stehen in `scripts/lang/*.msg`. Neue englische
  Optionen `--no-ai`, `--no-search`, `--no-service`, `--backup-only`, `--no-backup` bzw. `-BackupOnly`, `-NoBackup`, `-Keep`,
  `-TimeoutSeconds`; die deutschen Namen funktionieren weiter. `KEEP` ersetzt `BEHALTEN`.
- Alle Shell-Skripte sind im Repository als ausführbar markiert (`update.sh` war es nicht: `./scripts/update.sh` scheiterte).
- Linux-Installer: Der Gesundheitstest und die Einstellungen nutzen `127.0.0.1` statt `localhost`; die Adresse für Handys
  kommt von der Standardroute statt von der ersten Adresse von `hostname -I`.
- Windows-Installer: Die Adresse für Handys ist die des Netzwerkadapters mit Gateway (vorher wurde teils ein virtueller
  WSL-/Hyper-V-Adapter genannt); ein harmloser PostgreSQL-Hinweis mit kaputten Zeichen entfällt.
- Der Windows-Installer legt die geplante Aufgabe und die Firewall-Regel jetzt als „Famulus DMS“ an (vorher
  „HomeDMS“); gleichnamige alte Einträge räumt er beim Lauf weg.
- Doku: Installation ohne Docker in der `README.md`, Hinweis zu Docker und Port-Konflikten,
  Skriptübersicht in `scripts/README.md`, kaputter `mv`-Befehl der Linux-Anleitung korrigiert.
- Der Windows-Installer läuft in mehreren Sprachen: je ein Skript für Deutsch, English und Русский
  (`install-windows.de.ps1`, `.en.ps1`, `.ru.ps1`); `install-windows.ps1` wählt die Sprache nach der
  Windows-Anzeigesprache oder per `-Language`. Die Installationslogik und der Code sind jetzt englisch, alle Meldungen
  stehen in `scripts/lang/`. Parameter heißen `-DataFolder`, `-NoAI`, `-WithSearch`; die deutschen Namen
  (`-DatenOrdner`, `-OhneKI`, `-MitSuche`) funktionieren weiter. Der Name der Passwortdatei des Datenbank-Admins
  ist jetzt `postgres-admin-password.txt` (die alte Datei wird weiter gefunden).
- Der Windows-Installer fragt beim ersten Lauf nach dem Datenordner für
  Dokumente, Scan-Ordner und Protokolle (Vorschlag `C:\Famulus-Data`, vorher fest `C:\HomeDMS-Daten`).
  Bei einem erneuten Lauf wird der bisherige Ordner aus der `homedms.env` übernommen; mit
  `-DatenOrdner` entfällt die Rückfrage.
- Fehlerkorrektur im Starter ohne Docker (`python -m homedms.server`): `PORT` und `HOST` aus der
  `homedms.env` wurden ignoriert, er belegte immer Port 8000.
- Fehlerkorrektur Texterkennung unter Windows: Der eigene Sprachordner wurde Tesseract als
  `--tessdata-dir "…"` mit Anführungszeichen im Pfad übergeben, die unter Windows im Pfad blieben
  („Error opening data file“). Gescannte PDFs und Fotos ließen sich dort nicht lesen. Er wird jetzt über
  `TESSDATA_PREFIX` bekannt gemacht (auch mit Leerzeichen im Pfad). Unter Linux/Docker ändert sich nichts.
- Der Gesundheitstest des Windows-Installers nutzt `127.0.0.1` statt `localhost` (auf manchen PCs läuft
  `::1` in ein Zeitlimit) und bricht den Installer nicht mehr ab; die Firewall-Regel legt er per `netsh` an.
- Der Haushaltsname ist bei der Ersteinrichtung optional. Ohne Angabe heißt der Haushalt **„Home“**
  (statt dass die Einrichtung ohne Namen abbricht oder ein Platzhalter wie „string“ in der Ablage
  landet). Der Name ist zugleich der oberste Ordner der Dateiablage und lässt sich später unter
  „Profil & Haushalt“ ändern.
- Die Ordner im Scan-Ordner heißen jetzt `_imported` (importierte Originale) und `_failed`
  (Unbrauchbares) statt `_importiert` und `_fehler`. Vorhandene Ordner mit den alten Namen werden beim
  nächsten Lauf automatisch umbenannt, es gehen keine Dateien verloren und nichts wird doppelt importiert.
  Gibt es den neuen Ordner schon, bleibt der alte unverändert liegen und wird weiter übersprungen.
  Wer Skripte oder Freigaben auf die alten Namen eingerichtet hat, muss sie anpassen.
- Neuer Name: **Famulus DMS** (vorher „HomeDMS“). Repository und Image heißen `famulus-dms`
  (`ghcr.io/sschneidt/famulus-dms`). Technisch bleibt alles beim Alten: Python-Paket `homedms`,
  Docker-Projektname `homedms` (deine Daten bleiben erhalten), die Kopfzeile `X-HomeDMS-Session`,
  Datenbankname und der Windows-Dienst `HomeDMS`.
- In der Zwei-Faktor-App erscheint ein neu eingerichtetes Konto als „Famulus DMS“. Bereits
  eingerichtete Konten funktionieren unverändert weiter.

## [0.1.0] – 2026-10-06

Erster Stand mit Versionsnummer.

### Neu
- Papierkorb wird nachts automatisch geleert: Dokumente, die länger als 30 Tage
  (`TRASH_RETENTION_DAYS`) im Papierkorb liegen, werden endgültig gelöscht – samt Dateien und
  Suchindex-Eintrag.
- Die installierte Version steht in der API-Antwort der Diagnose (`/api/v1/system/diagnostics`).
- Update-Skripte `scripts/update.ps1` (Windows) und `scripts/update.sh` (Linux/NAS): sichern vor
  jedem Update die Datenbank und prüfen danach, ob Famulus DMS wieder läuft.
