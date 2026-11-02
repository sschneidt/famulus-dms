# Installation auf einer Synology-NAS

Gedacht für: **DS1520+** (Intel-Celeron-Prozessor, x86_64, 8 GB RAM) mit **DSM 7.4** und
*Container Manager*. Andere Intel/AMD-Modelle mit DSM 7.2 oder neuer funktionieren genauso. Modelle mit
ARM-Prozessor (viele J-, Play- und Value-Modelle) gehen **nicht**, weil das Image nur für `amd64`
gebaut wird.

Die Installation besteht aus **einer einzigen Datei** (`docker-compose.synology.yml`), die du im Container Manager
als Projekt anlegst. Du brauchst weder SSH noch eine `.env`-Datei noch den Quellcode. Passwörter und Schlüssel
erzeugt Famulus DMS beim ersten Start selbst. Die Menünamen können je nach DSM-Version leicht abweichen.

## 1. Vorbereiten (in DSM)

1. **Container Manager** installieren (Paket-Zentrum).
2. **Freigegebenen Ordner anlegen:** Systemsteuerung → Freigegebener Ordner → Erstellen, Name `famulus`, auf einem
   Volume mit genug Platz. Papierkorb und Verschlüsselung brauchst du nicht.
3. **Unterordner anlegen** (Dateistation, im Ordner `famulus`):

   | Ordner | Zweck |
   |---|---|
   | `app` | Ordner des Projekts (nimmt die Compose-Datei auf) |
   | `documents` | die abgelegten Dokumente |
   | `scan` | Scan-Ordner, in den der Scanner per SMB speichert |
   | `backups` | Datenbanksicherungen (siehe Abschnitt 6) |

   Die Datenbank, der Suchindex und die KI-Modelle liegen in Docker-Volumes und brauchen keinen eigenen Ordner.
4. **SMB aktivieren:** Systemsteuerung → Dateidienste → SMB (für den Scanner und den Zugriff vom PC).

## 2. Die Datei besorgen

Das Repository ist öffentlich, du brauchst kein GitHub-Konto. Lade auf dem PC diese Datei herunter
(Rechtsklick → *Link speichern unter*):

```
https://raw.githubusercontent.com/sschneidt/famulus-dms/main/docker-compose.synology.yml
```

Ab Version 0.2.2 hängt sie auch an jedem [Release](https://github.com/sschneidt/famulus-dms/releases).

Öffne sie in einem Texteditor und ändere **nur**, wenn nötig:

- Liegt der Ordner `famulus` nicht auf `volume1`, ersetze `/volume1/famulus` überall durch deinen Pfad (Suchen und
  Ersetzen, 6 Stellen).
- Stimmt die Zeitzone nicht, ersetze `Europe/Berlin`.

Alles andere kann so bleiben.

## 3. Projekt anlegen und starten

1. Container Manager → **Projekt** → **Erstellen**.
2. **Projektname: `homedms`**. Diesen Namen unbedingt so lassen, auch wenn die Anwendung jetzt Famulus DMS heißt:
   Die Datenvolumes heißen danach.
3. **Pfad:** `/volume1/famulus/app`. Als Quelle die Datei `docker-compose.synology.yml` **hochladen** (oder
   *docker-compose.yml erstellen* wählen und den Inhalt der Datei einfügen).
4. Weiter, den Web-Station-Schritt überspringen, bestätigen. Das Projekt startet.

Beim ersten Start lädt Docker die Images (einige GB) und das KI-Modell. Das dauert je nach Leitung 10 bis 30
Minuten. Den Fortschritt siehst du im Container Manager unter **Projekt → homedms** und unter **Container**.
Der Container `ollama-init` lädt das Modell und beendet sich danach von selbst (Status *Beendet*, das ist normal).

**Einrichtungscode:** Container `homedms-app-api-1` → *Details* → **Protokoll**, dort nach „Einrichtungscode“ suchen.

Falls die DSM-Firewall aktiv ist, müssen die Ports **8000** und **8443** für dein Heimnetz erlaubt sein
(Systemsteuerung → Sicherheit → Firewall).

## 4. Ersteinrichtung im Browser

Öffne `https://<nas-adresse>:8443` (die IP-Adresse oder den Namen deiner NAS). Der Browser warnt, weil das Zertifikat
aus deinem eigenen Heimnetz stammt. Das ist beim ersten Mal normal; bestätige die Ausnahme.

Im Einrichtungsassistenten gibst du den Einrichtungscode, deinen Haushalt und das Admin-Konto ein. Das Feld
**„Adresse dieses Servers im Heimnetz“** ist mit der Adresse vorbelegt, die du gerade im Browser benutzt. Trage dort
zusätzlich weitere Namen ein, unter denen du die NAS erreichst, durch Komma getrennt (z. B. `192.168.1.10, nas.local`).
Für diese Adressen stellt Famulus DMS das HTTPS-Zertifikat aus. Ohne die richtige Adresse warnt der Browser auf Handy und
PC dauerhaft.

Danach vertraut jedes Gerät dem Zertifikat einmalig über `http://<nas-adresse>:8000/zertifikat` (Anleitung mit QR-Code
für iPhone, Android, Windows und Mac).

> Eine Adresse nachträglich ergänzen: Trage sie in der Compose-Datei bei `TLS_HOSTNAMES` ein (Projekt bearbeiten) und
> starte das Projekt neu. Die Seite *Diagnose* zeigt dir, welche Adressen das Zertifikat noch nicht abdeckt.

## 5. Leistung auf der DS1520+

- **RAM:** 8 GB reichen. Datenbank, Suche und Programm brauchen zusammen etwa 2 bis 3 GB. Das KI-Modell
  (`llama3.2:3b`, ca. 2 GB) wird nur bei Bedarf geladen und nach Inaktivität wieder entladen.
- **Geschwindigkeit:** Die NAS hat keine Grafikkarte, die KI läuft auf dem Prozessor und ist dadurch
  langsam (Sekunden bis Minuten pro Dokument, im Hintergrund). Die Texterkennung und die Suche sind davon
  nicht betroffen. Wenn es zu lahm ist, nimm ein kleineres Modell: In der Compose-Datei `llama3.2:3b` durch
  `llama3.2:1b` ersetzen (3 Stellen), das Projekt bearbeiten und neu starten.
- **Prozessor ohne AVX:** Der Celeron der DS1520+ hat keine AVX-Befehle. Ollama läuft dort in einer
  langsameren Rückfallvariante. Sollte der Container `ollama` nicht starten oder abstürzen, schick mir sein
  Protokoll (Container → ollama → Details → Protokoll). Ohne KI funktionieren Ablage, Texterkennung, Suche und
  Wiedervorlagen weiterhin, nur die automatische Einordnung ist dann eingeschränkt.

## 6. Sichern und aktualisieren

**Datenbank sichern:** In Famulus DMS unter **Diagnose → Datenbanksicherung → Jetzt sichern**. Die Sicherung landet
im Ordner `famulus/backups` (die letzten 5 bleiben liegen); dort kannst du sie auch herunterladen oder löschen.

Sichere außerdem den ganzen Ordner `famulus` mit *Hyper Backup* (oder Snapshot Replication). Das erfasst die Dokumente,
den Scan-Ordner und die Datenbanksicherungen. Die Docker-Volumes (laufende Datenbank, Suchindex) werden von einer reinen
Ordner-Sicherung **nicht** erfasst. Verlass dich deshalb auf die Sicherungen aus der Diagnose-Seite. Wiederherstellen:
[Updates.md](Updates.md), Abschnitt 3.

**Aktualisieren:**

1. Erst eine Sicherung anlegen (siehe oben).
2. Container Manager → **Projekt → homedms** → **Aktion → Erstellen** (englisch: *Build*). Das lädt die neueren Images
   und startet die Container neu. Datenbankänderungen laufen dabei automatisch.
3. Was sich geändert hat, steht im [Änderungsprotokoll](../CHANGELOG.md).

Möchtest du nur bewusst eine bestimmte Version, ersetze in der Compose-Datei `famulus-dms:latest` durch die
Versionsnummer, z. B. `famulus-dms:0.2.2`.

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
| Projekt lässt sich nicht erstellen | Projektname `homedms`, Pfad `/volume1/famulus/app` und die Ordner `documents`, `scan`, `backups` müssen existieren |
| Seite nicht erreichbar | Läuft der Container `homedms-app-api-1`? Ports 8000/8443 und Firewall prüfen |
| Zertifikatswarnung | Beim ersten Mal normal; danach Anleitung unter `http://<nas>:8000/zertifikat`. Warnt der Browser weiter, fehlt die Adresse im Zertifikat (siehe Abschnitt 4) |
| Scanner-Dateien werden nicht abgeholt | Schreibrechte des Scanner-Benutzers auf den Scan-Ordner prüfen |
| Sicherung nicht möglich | Seite *Diagnose* → Datenbanksicherung zeigt die Meldung; der Ordner `backups` muss beschreibbar sein |
| Speicher knapp | kleineres Modell (siehe Abschnitt 5) oder RAM-Erweiterung (die DS1520+ nimmt bis zu 20 GB) |

## Alternative: per SSH

Wer SSH nutzt (Systemsteuerung → Terminal & SNMP → SSH-Dienst aktivieren, Benutzer in der Gruppe *administrators*),
kann statt der Oberfläche diese Befehle verwenden:

```bash
cd /volume1/famulus/app            # dort liegt docker-compose.synology.yml
sudo docker compose -f docker-compose.synology.yml up -d          # starten
sudo docker compose -f docker-compose.synology.yml pull && sudo docker compose -f docker-compose.synology.yml up -d   # aktualisieren
sudo docker compose -f docker-compose.synology.yml logs app-api | grep -i einrichtungscode
```
