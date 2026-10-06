# Änderungsprotokoll – Famulus DMS

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach
[Semantic Versioning](https://semver.org/lang/de/): `MAJOR.MINOR.PATCH` – Fehlerkorrekturen
erhöhen die letzte Stelle, neue Funktionen die mittlere, unverträgliche Änderungen die erste.
Ablauf eines Releases und eines Updates: [docs/Updates.md](docs/Updates.md).

## [Unveröffentlicht]

### Geändert
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
