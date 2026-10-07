# Updates und Releases

Für alle, die Famulus DMS betreiben (Abschnitt 1–4), und für alle, die neue Versionen herausgeben (Abschnitt 5).

## 1. Versionen

Famulus DMS nutzt [Semantic Versioning](https://semver.org/lang/de/) `MAJOR.MINOR.PATCH`:

| Änderung | Beispiel | Was das für dich heißt |
|---|---|---|
| Fehlerkorrektur | 1.2.0 → 1.2.1 | gefahrlos einspielen |
| neue Funktion | 1.2.1 → 1.3.0 | einspielen, vorher kurz ins Änderungsprotokoll schauen |
| unverträgliche Änderung | 1.3.0 → 2.0.0 | im Änderungsprotokoll steht, was du tun musst |

- Was sich geändert hat, steht im [CHANGELOG.md](../CHANGELOG.md).
- Die installierte Version siehst du als Admin in der Antwort von `/api/v1/system/diagnostics` (Feld `version`). Eine Anzeige in der Oberfläche folgt.
- Docker-Images tragen dieselben Nummern: `1.2.3` (genau diese Version), `1.2` (immer das neueste 1.2.x) und `latest`.

## 2. Update mit Docker (Synology, Windows, Linux)

Windows (aus dem Famulus-DMS-Ordner):

```
.\scripts\update.de.cmd
```

Linux / NAS:

```bash
./scripts/update.de.sh
```

Je Sprache ein Skript: `update.de.*` (Deutsch), `update.en.*` (English), `update.ru.*` (Русский). `update.cmd` und `update.sh` wählen die Sprache nach der Systemsprache; `-Language de|en|ru` bzw. `--lang de|en|ru` legt sie fest. Die Texte stehen in `scripts/lang/update.<Sprache>.msg`.

Das Skript macht der Reihe nach:

1. **Datenbank sichern** nach `backups/homedms-<Version>-<Datum>.dump`. Die letzten 5 Sicherungen bleiben liegen. Schlägt die Sicherung fehl, wird nichts verändert.
2. **Neue Version holen:** Zeigt `APP_IMAGE` in der `.env` auf eine Registry (Standard: `ghcr.io/sschneidt/famulus-dms`), wird das fertige Image geladen. Steht dort ein lokaler Name wie `homedms/backend` (Entwicklung), wird aus dem Ordner gebaut (bei einem Git-Ordner vorher `git pull`).
3. **Neu starten.** Die Datenbank-Änderungen der neuen Version laufen dabei automatisch.
4. **Prüfen**, ob Famulus DMS wieder antwortet, und die alte und neue Version melden.

Deine Dokumente, der Scan-Ordner, der Suchindex und die KI-Modelle liegen in Volumes und Ordnern außerhalb der Container und bleiben unberührt.

**Eine bestimmte Version festlegen:** `APP_VERSION=1.2` in der `.env` (statt `latest`), danach das Update-Skript starten. Wer lieber nur Fehlerkorrekturen bekommen will, bleibt bei `1.2`, bis er bewusst auf `1.3` wechselt.

Optionen: `-BackupOnly` / `--backup-only` (deutsch: `-NurSichern` / `--nur-sichern`) sichert nur die Datenbank. `-NoBackup` / `--no-backup` (deutsch: `-OhneSicherung` / `--ohne-sicherung`) überspringt die Sicherung (nicht empfohlen). Wie viele Sicherungen bleiben: `-Keep 5` bzw. `KEEP=5` (früher `-Behalten` / `BEHALTEN`).

### Wichtig: Sicherung der Dokumente

Das Skript sichert die **Datenbank**, nicht die Dokumente-Dateien. Die liegen im Ordner `DOCUMENTS_PATH` und gehören zusätzlich in deine normale Datensicherung (Synology: Hyper Backup, siehe Anforderungsdokument 4.6). Ohne beides lässt sich ein Haushalt nicht vollständig wiederherstellen.

## 3. Zurück zur alten Version

Datenbank-Änderungen lassen sich nicht automatisch rückgängig machen. Ein Rückweg besteht deshalb aus **altem Programmstand plus passender Datenbank-Sicherung**:

1. In der `.env` die alte Version eintragen (`APP_VERSION=1.2.1`). Bei einem selbst gebauten Stand: den alten Git-Stand auschecken (`git checkout v1.2.1`).
2. Famulus DMS stoppen: `docker compose stop app-api app-worker`
3. Die Sicherung einspielen (Dateiname anpassen):

   ```bash
   docker compose cp backups/homedms-1.2.1-20261006-183917.dump db:/tmp/restore.dump
   docker compose exec db sh -c 'pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean --if-exists --no-owner /tmp/restore.dump'
   docker compose exec db rm /tmp/restore.dump
   ```

4. Starten: `docker compose up -d` (mit `--build`, wenn du aus dem Ordner baust).

Dokumente, die du **nach** dem Update hinzugefügt hast, fehlen danach in der Datenbank, ihre Dateien bleiben aber im Dokumente-Ordner liegen.

## 4. Update ohne Docker (Windows-PC, Linux-Server)

Siehe [Installation-ohne-Docker.md](Installation-ohne-Docker.md), Abschnitt „Update“: neuen Stand des Ordners einspielen und das Installationsskript erneut starten. Sichere vorher die Datenbank mit `pg_dump`.

## 5. Neue Version herausgeben (für Entwickler)

Einmalig: das Repository liegt auf GitHub, unter *Settings → Actions → General → Workflow permissions* ist „Read and write“ erlaubt.

Für jedes Release:

1. Die Version in **drei Dateien** gleich setzen: `backend/homedms/__init__.py`, `backend/pyproject.toml` und ein neuer Abschnitt `## [X.Y.Z] – JJJJ-MM-TT` im `CHANGELOG.md` (der Test `tests/test_version.py` meldet, wenn sie auseinanderlaufen).
2. Committen und pushen, dann den Tag setzen:

   ```bash
   git tag v1.3.0
   git push origin v1.3.0
   ```

3. GitHub Actions (`.github/workflows/release.yml`) erledigt den Rest: prüft, dass Tag, Code und Änderungsprotokoll zusammenpassen, lässt alle Tests laufen, baut das Image, veröffentlicht es als `ghcr.io/sschneidt/famulus-dms:1.3.0`, `:1.3` und `:latest` und legt ein GitHub-Release mit dem Text aus dem Änderungsprotokoll an.
4. Das erste Mal: das Paket unter *GitHub → Packages → famulus-dms → Package settings* auf **öffentlich** stellen, sonst können andere das Image nicht laden.

### Regeln für Datenbank-Änderungen

Anwender springen oft über mehrere Versionen auf einmal, und ein Rückweg geht nur über die Sicherung. Deshalb:

- Schema-Änderungen **ausschließlich** als neue Alembic-Migration. Bereits veröffentlichte Migrationen werden nie verändert.
- Erst hinzufügen, später entfernen: Neue Spalten sind zunächst optional oder haben einen Standardwert. Eine Spalte, die die neue Version nicht mehr braucht, fliegt frühestens ein Release später raus.
- Jede Migration muss auf einer Datenbank mit Daten laufen, nicht nur auf einer leeren. Die Integrationstests (`alembic upgrade head`) prüfen das nur für den leeren Fall, bei größeren Umbauten also von Hand gegen eine Kopie der echten Datenbank testen.
- Größere Umbauten gehören in ein Major-Release (2.0.0) und bekommen im Änderungsprotokoll einen Abschnitt „Was du tun musst“.
