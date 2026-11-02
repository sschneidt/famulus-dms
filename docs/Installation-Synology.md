# Installation auf einer Synology-NAS

Gedacht für: **DS1520+** (Intel-Celeron-Prozessor, x86_64, 8 GB RAM) mit **DSM 7.4** und
*Container Manager*. Andere Intel/AMD-Modelle mit DSM 7.2 oder neuer funktionieren genauso. Modelle mit
ARM-Prozessor (viele J-, Play- und Value-Modelle) gehen **nicht**, weil das Image nur für `amd64`
gebaut wird.

Die Anleitung kommt **ohne SSH** aus: Alles läuft über die DSM-Oberfläche (Systemsteuerung, Dateistation,
Container Manager, Aufgabenplaner) und einen Windows-/Mac-PC. Die Menünamen können je nach DSM-Version leicht
abweichen. Wer SSH bevorzugt, findet die Befehle am Ende.

## 1. Vorbereiten (in DSM)

1. **Container Manager** installieren (Paket-Zentrum).
2. **Freigegebenen Ordner anlegen:** Systemsteuerung → Freigegebener Ordner → Erstellen, Name `famulus`, auf einem
   Volume mit genug Platz. Papierkorb und Verschlüsselung brauchst du nicht.
3. **Unterordner anlegen** (Dateistation, im Ordner `famulus`):

   | Ordner | Zweck |
   |---|---|
   | `app` | Programmdateien und Einstellungen (`.env`) |
   | `documents` | die abgelegten Dokumente |
   | `scan` | Scan-Ordner, in den der Scanner per SMB speichert |

   Die Datenbank, der Suchindex und die KI-Modelle liegen in Docker-Volumes und brauchen keinen eigenen Ordner.
4. **SMB aktivieren:** Systemsteuerung → Dateidienste → SMB. Damit erreichst du die NAS vom PC unter
   `\\<nas>\famulus`.

## 2. Einstellungen am PC vorbereiten

Das Repository ist öffentlich, du brauchst kein GitHub-Konto.

1. Auf dem PC die ZIP-Datei der aktuellen Version laden und entpacken, z. B.
   `https://github.com/sschneidt/famulus-dms/archive/refs/tags/v0.2.1.zip`
   (die neueste Version steht unter [Releases](https://github.com/sschneidt/famulus-dms/releases)).
   Es entsteht ein Ordner `famulus-dms-0.2.1`.
2. In diesem Ordner die Datei `docker-compose.override.yml` **löschen** (nur für die Entwicklung).
3. Die Datei `.env.de.example` **kopieren** und die Kopie in `.env` umbenennen.
4. `.env` mit einem Texteditor öffnen (z. B. Notepad++ oder VS Code, als UTF-8 speichern) und diese Werte
   anpassen:

   ```ini
   POSTGRES_PASSWORD=<eigenes Passwort>
   MEILI_MASTER_KEY=<mindestens 16 Zeichen>
   JWT_SECRET=<lange Zufallszeichen>
   DOCUMENTS_PATH=/volume1/famulus/documents
   SCAN_FOLDER_PATH=/volume1/famulus/scan
   TLS_HOSTNAMES=<nas-name>,<nas-name>.local,<IP-Adresse der NAS>
   TZ=Europe/Berlin
   ```

   Die Werte nach dem `=` ohne Anführungszeichen und ohne Kommentar in derselben Zeile schreiben.
   Passwörter und Schlüssel erzeugst du zum Beispiel in der Windows-PowerShell mit:

   ```powershell
   -join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Maximum 256) })
   ```

   Den Befehl dreimal ausführen, für jeden Wert eine eigene Zeichenfolge.

## 3. Dateien auf die NAS kopieren

Den **gesamten Inhalt** des Ordners `famulus-dms-0.2.1` (inklusive der Datei `.env`) nach `\\<nas>\famulus\app`
kopieren, im Windows-Explorer oder per Hochladen in der Dateistation. Danach liegen z. B. `docker-compose.yml`,
`.env` und der Ordner `init` direkt in `famulus/app`.

Die Datei `.env` beginnt mit einem Punkt und gilt als versteckt. In der Dateistation siehst du sie erst, wenn du
unter *Einstellungen* die Anzeige versteckter Dateien einschaltest.

## 4. Projekt starten (Container Manager)

1. Container Manager → **Projekt** → **Erstellen**.
2. **Projektname: `homedms`**. Diesen Namen unbedingt so lassen, auch wenn die Anwendung jetzt Famulus DMS heißt.
   Die Datenvolumes heißen danach, und die Update-Skripte erwarten ihn.
3. **Pfad:** `/volume1/famulus/app` wählen. Bei der Quelle *Vorhandene docker-compose.yml verwenden* auswählen.
4. Auf *Weiter* klicken. Den Web-Station-Schritt überspringen, dann bestätigen und starten.

Beim ersten Start lädt Docker die Images (einige GB) und das KI-Modell. Das dauert je nach Leitung 10 bis 30
Minuten. Den Fortschritt siehst du im Container Manager unter **Projekt → homedms** und unter **Container**.
Der Container `ollama-init` lädt das Modell und beendet sich danach von selbst (Status *Beendet*, das ist normal).

**Prüfen, ob die `.env` gelesen wurde:** Öffne unter *Container* den Container `homedms-app-api-1` →
*Einstellungen/Details* → Umgebung. Dort muss unter `TLS_HOSTNAMES` dein Name stehen und nicht leer sein. Wenn
die Werte fehlen, hat der Container Manager die `.env` nicht übernommen. Melde dich dann (siehe Problemlösung).

**Einrichtungscode für den Assistenten:** Container `homedms-app-api-1` → *Details* → **Protokoll**, dort nach
„Einrichtungscode“ suchen.

Dann im Browser `https://<nas>:8443` öffnen und dem Einrichtungsassistenten folgen. Für neue Geräte steht die
Anleitung zum Zertifikat auf `http://<nas>:8000/zertifikat`.

Falls die DSM-Firewall aktiv ist, müssen die Ports **8000** und **8443** für dein Heimnetz erlaubt sein
(Systemsteuerung → Sicherheit → Firewall).

## 5. Leistung auf der DS1520+

- **RAM:** 8 GB reichen. Datenbank, Suche und Programm brauchen zusammen etwa 2 bis 3 GB. Das KI-Modell
  (`llama3.2:3b`, ca. 2 GB) wird nur bei Bedarf geladen und nach Inaktivität wieder entladen.
- **Geschwindigkeit:** Die NAS hat keine Grafikkarte, die KI läuft auf dem Prozessor und ist dadurch
  langsam (Sekunden bis Minuten pro Dokument, im Hintergrund). Die Texterkennung und die Suche sind davon
  nicht betroffen. Wenn es zu lahm ist, nimm ein kleineres Modell: In der `.env` `OLLAMA_CHAT_MODEL=llama3.2:1b`
  eintragen, dann im Container Manager das Projekt anhalten und wieder starten (oder *Erstellen/Neu erstellen*).
- **Prozessor ohne AVX:** Der Celeron der DS1520+ hat keine AVX-Befehle. Ollama läuft dort in einer
  langsameren Rückfallvariante. Sollte der Container `ollama` nicht starten oder abstürzen, schick mir sein
  Protokoll (Container → ollama → Details → Protokoll). Ohne KI funktionieren Ablage, Texterkennung, Suche und
  Wiedervorlagen weiterhin, nur die automatische Einordnung ist dann eingeschränkt.

## 6. Aktualisieren und sichern

**Aktualisieren** sichert vorher die Datenbank (siehe [Updates.md](Updates.md)). Ohne SSH geht das über den
Aufgabenplaner:

1. Systemsteuerung → **Aufgabenplaner** → Erstellen → *Geplante Aufgabe* → *Benutzerdefiniertes Skript*.
2. Allgemein: Name `Famulus DMS aktualisieren`, Benutzer **root**. Den Haken bei *Aktiviert* entfernst du, dann läuft
   die Aufgabe nur auf Knopfdruck.
3. Aufgabeneinstellungen → Benutzerdefiniertes Skript:

   ```bash
   cd /volume1/famulus/app && bash ./scripts/update.sh
   ```

4. Speichern. Zum Aktualisieren markierst du die Aufgabe und klickst **Ausführen**. Das Ergebnis siehst du unter
   *Aktion → Ergebnis anzeigen*. Als zweite Aufgabe mit `bash ./scripts/update.sh --backup-only` legst du eine
   reine Datenbanksicherung an, die du auch regelmäßig planen kannst.

Sichern solltest du zusätzlich den Ordner `famulus` mit *Hyper Backup* (oder Snapshot Replication). Die
Datenbanksicherungen von `update.sh` landen in `famulus/app/backups`. Die Docker-Volumes (Datenbank, Suchindex)
werden von einer reinen Ordner-Sicherung nicht erfasst. Verlass dich deshalb auch auf diese SQL-Sicherungen.

## 7. Scanner anbinden (eigener Benutzer)

Der Scanner schreibt per SMB in den Ordner `scan`. Gib ihm dafür einen eigenen Benutzer, damit er nie an deine
Dokumente kommt:

1. **Benutzer anlegen:** Systemsteuerung → Benutzer & Gruppe → Erstellen, z. B. `scanner` mit eigenem Passwort,
   das nur im Scanner eingetragen wird.
2. **Berechtigungen:** Der Benutzer `scanner` braucht Lesen/Schreiben auf die Freigabe mit dem Scan-Ordner und
   sonst keinen Zugriff, vor allem nicht auf `documents`. Die Rechte vergibst du in der Dateistation am Ordner
   `scan` (Rechtsklick → Eigenschaften → Berechtigungen). Auf der Freigabe `famulus` darf er den Ordner nur durchlaufen
   (Rechte *Ordner durchsuchen*); wenn dir das zu fummelig ist, lege `scan` als eigene Freigabe an.
3. **SMB** muss aktiv sein (siehe Abschnitt 1).
4. **Im Scanner** als Ziel `\\<nas>\<freigabename>` mit diesem Benutzer eintragen.

Famulus DMS selbst braucht keinen eigenen Benutzer: Die Container laufen als `root` und holen die Dateien
jede Minute ab. Danach verschiebt es sie nach `_imported/` bzw. `_failed/`. Diese Unterordner und
verschobenen Dateien gehören dann `root`; der Benutzer `scanner` kann sie nicht mehr lesen, das ist unkritisch.
Wenn du selbst in `_failed/` nachsehen oder aufräumen willst, gib deinem normalen Benutzer
*Lesen/Schreiben* auf die `scan`-Freigabe. Falls du dort etwas nicht löschen darfst, passe die Rechte der
Unterordner in der Dateistation an.

## Problemlösung

| Problem | Lösung |
|---|---|
| Projekt lässt sich nicht erstellen | Prüfe, ob `docker-compose.yml` und `.env` direkt in `famulus/app` liegen und nicht in einem Unterordner |
| Werte aus der `.env` kommen nicht an | Im Container Manager die Umgebung von `homedms-app-api-1` prüfen. Hilft das nicht, den SSH-Weg unten verwenden |
| Seite nicht erreichbar | Läuft der Container `homedms-app-api-1`? Ports 8000/8443, Firewall und richtige IP in `TLS_HOSTNAMES` prüfen |
| Zertifikatswarnung | Normal beim ersten Mal, Anleitung unter `http://<nas>:8000/zertifikat` |
| Scanner-Dateien werden nicht abgeholt | Schreibrechte des Scanner-Benutzers auf den Scan-Ordner prüfen |
| Speicher knapp | kleineres Modell (siehe Abschnitt 5) oder RAM-Erweiterung (die DS1520+ nimmt bis zu 20 GB) |

## Alternative: per SSH

Wer SSH nutzt (Systemsteuerung → Terminal & SNMP → SSH-Dienst aktivieren, Benutzer in der Gruppe
*administrators*), ersetzt die Abschnitte 2 bis 4 durch:

```bash
cd /volume1/famulus/app
sudo curl -L https://github.com/sschneidt/famulus-dms/archive/refs/tags/v0.2.1.tar.gz -o famulus.tar.gz
sudo tar xzf famulus.tar.gz --strip-components=1
sudo rm famulus.tar.gz docker-compose.override.yml
sudo cp .env.de.example .env
sudo vi .env                 # Werte wie in Abschnitt 2 eintragen
sudo docker compose up -d
sudo docker compose logs app-api | grep -i einrichtungscode
```

Aktualisieren: `sudo bash ./scripts/update.sh`. Nur sichern: `sudo bash ./scripts/update.sh --backup-only`.
