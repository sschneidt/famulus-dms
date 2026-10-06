# Änderungsprotokoll – Famulus DMS

Format nach [Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach
[Semantic Versioning](https://semver.org/lang/de/): `MAJOR.MINOR.PATCH` – Fehlerkorrekturen
erhöhen die letzte Stelle, neue Funktionen die mittlere, unverträgliche Änderungen die erste.
Ablauf eines Releases und eines Updates: [docs/Updates.md](docs/Updates.md).

## [Unveröffentlicht]

### Geändert
- Der Windows-Installer (`scripts/install-windows.ps1`) fragt beim ersten Lauf nach dem Datenordner für
  Dokumente, Scan-Ordner und Protokolle (Vorschlag `C:\Famulus-Daten`, vorher fest `C:\HomeDMS-Daten`).
  Bei einem erneuten Lauf wird der bisherige Ordner aus der `homedms.env` übernommen; mit
  `-DatenOrdner` entfällt die Rückfrage.
- Fehlerkorrektur im Starter ohne Docker (`python -m homedms.server`): `PORT` und `HOST` aus der
  `homedms.env` wurden ignoriert, er belegte immer Port 8000.
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
