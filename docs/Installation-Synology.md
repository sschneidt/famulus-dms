# Installation auf einer Synology-NAS

Gedacht für: **DS1520+** (Intel-Celeron-Prozessor, x86_64, 8 GB RAM) mit **DSM 7.4** und
*Container Manager*. Andere Intel/AMD-Modelle mit DSM 7.2 oder neuer funktionieren genauso. Modelle mit
ARM-Prozessor (viele J-, Play- und Value-Modelle) gehen **nicht**, weil das Image nur für `amd64`
gebaut wird.

## 1. Vorbereiten

1. **Container Manager** installieren (Paket-Zentrum).
2. **SSH aktivieren:** Systemsteuerung → Terminal & SNMP → *SSH-Dienst aktivieren*. Danach mit
   `ssh <benutzer>@<nas>` anmelden. Der Benutzer muss zur Gruppe *administrators* gehören.
   (SSH kannst du nach der Installation wieder abschalten.)
3. **Ordner anlegen** (Dateistation, in einem Volume mit genug Platz):

   | Ordner | Zweck |
   |---|---|
   | `/volume1/famulus/app` | Programmdateien und Einstellungen (`.env`) |
   | `/volume1/famulus/dokumente` | die abgelegten Dokumente |
   | `/volume1/famulus/scan` | Scan-Ordner, in den der Scanner per SMB speichert |

   Den Ordner `scan` kannst du in der Systemsteuerung unter *Freigegebener Ordner* für den Scanner
   freigeben. Die Datenbank, der Suchindex und die KI-Modelle liegen in Docker-Volumes und brauchen
   keinen eigenen Ordner.

## 2. Programmdateien holen

Per SSH (das Repository ist öffentlich, es ist keine Anmeldung nötig):

```bash
cd /volume1/famulus/app
sudo curl -L https://github.com/sschneidt/famulus-dms/archive/refs/tags/v0.2.1.tar.gz -o famulus.tar.gz
sudo tar xzf famulus.tar.gz --strip-components=1
sudo rm famulus.tar.gz docker-compose.override.yml
```

`docker-compose.override.yml` ist nur für die Entwicklung gedacht und wird nicht gebraucht.
Die Version `v0.2.1` kannst du durch die aktuelle ersetzen (siehe [Releases](https://github.com/sschneidt/famulus-dms/releases)).

## 3. Einstellungen

```bash
sudo cp .env.de.example .env
sudo vi .env
```

Diese Werte anpassen (in `vi`: `i` zum Bearbeiten, `Esc` und dann `:wq` zum Speichern):

```ini
POSTGRES_PASSWORD=<eigenes Passwort>
MEILI_MASTER_KEY=<mindestens 16 Zeichen>
JWT_SECRET=<lange Zufallszeichen, z. B. Ausgabe von: openssl rand -hex 32>
DOCUMENTS_PATH=/volume1/famulus/dokumente
SCAN_FOLDER_PATH=/volume1/famulus/scan
TLS_HOSTNAMES=<nas-name>,<nas-name>.local,<IP-Adresse der NAS>
TZ=Europe/Berlin
```

Zufallswerte erzeugst du mit `openssl rand -hex 32`. Die Werte nach dem `=` ohne Anführungszeichen und
ohne Kommentar in derselben Zeile schreiben.

## 4. Starten

```bash
cd /volume1/famulus/app
sudo docker compose up -d
```

Beim ersten Start lädt Docker die Images (einige GB) und das KI-Modell. Das dauert je nach Leitung
10 bis 30 Minuten. Den Fortschritt siehst du mit:

```bash
sudo docker compose ps
sudo docker compose logs -f ollama-init
```

Wenn `ollama-init` beendet ist (Status *exited (0)*), ist das Modell geladen.

Einrichtungscode für den Assistenten:

```bash
sudo docker compose logs app-api | grep -i einrichtungscode
```

Dann im Browser `https://<nas>:8443` öffnen und dem Einrichtungsassistenten folgen. Für neue Geräte
steht die Anleitung zum Zertifikat auf `http://<nas>:8000/zertifikat`.

Falls die DSM-Firewall aktiv ist, müssen die Ports **8000** und **8443** für dein Heimnetz erlaubt sein
(Systemsteuerung → Sicherheit → Firewall).

> **Hinweis zum Container Manager:** Du kannst das Projekt auch in der Oberfläche anlegen (Projekt →
> Erstellen, Pfad `/volume1/famulus/app`). Die Anleitung per SSH ist aber die verlässlichere Variante,
> weil `docker compose` die `.env` und die Image-Auswahl wie im Rest der Dokumentation behandelt.

## 5. Leistung auf der DS1520+

- **RAM:** 8 GB reichen. Datenbank, Suche und Programm brauchen zusammen etwa 2 bis 3 GB. Das KI-Modell
  (`llama3.2:3b`, ca. 2 GB) wird nur bei Bedarf geladen und nach Inaktivität wieder entladen.
- **Geschwindigkeit:** Die NAS hat keine Grafikkarte, die KI läuft auf dem Prozessor und ist dadurch
  langsam (Sekunden bis Minuten pro Dokument, im Hintergrund). Die Texterkennung und die Suche sind davon
  nicht betroffen. Wenn es zu lahm ist, nimm ein kleineres Modell: `OLLAMA_CHAT_MODEL=llama3.2:1b` in
  der `.env`, dann `sudo docker compose up -d`.
- **Prozessor ohne AVX:** Der Celeron der DS1520+ hat keine AVX-Befehle. Ollama läuft dort in einer
  langsameren Rückfallvariante. Sollte `ollama` nicht starten oder abstürzen, schick mir die Ausgabe von
  `sudo docker compose logs ollama`. Ohne KI funktionieren Ablage, Texterkennung, Suche und
  Wiedervorlagen weiterhin, nur die automatische Einordnung ist dann eingeschränkt.

## 6. Aktualisieren und sichern

Aktualisieren (sichert vorher die Datenbank, siehe [Updates.md](Updates.md)):

```bash
cd /volume1/famulus/app
sudo bash ./scripts/update.sh
```

Sichern solltest du zusätzlich den Ordner `/volume1/famulus` mit *Hyper Backup* (oder Snapshot
Replication). Die Datenbanksicherungen von `update.sh` landen in `/volume1/famulus/app/backups`.
Die Docker-Volumes (Datenbank, Suchindex) werden von einer reinen Ordner-Sicherung nicht erfasst.
Verlass dich deshalb auch auf diese SQL-Sicherungen, und starte sie bei Bedarf mit
`sudo bash ./scripts/update.sh --backup-only`.

## Problemlösung

| Problem | Lösung |
|---|---|
| `docker: command not found` | Container Manager nicht installiert, oder unter `sudo` fehlt der Pfad: `sudo /usr/local/bin/docker compose ...` |
| Seite nicht erreichbar | Ports 8000/8443 prüfen (`sudo docker compose ps`), Firewall, richtige IP in `TLS_HOSTNAMES` |
| Zertifikatswarnung | Normal beim ersten Mal, Anleitung unter `http://<nas>:8000/zertifikat` |
| Scanner-Dateien werden nicht abgeholt | Schreibrechte des Scanner-Benutzers auf `/volume1/famulus/scan` prüfen |
| Speicher knapp | kleineres Modell (siehe Abschnitt 5) oder RAM-Erweiterung (die DS1520+ nimmt bis zu 20 GB) |
