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

- Liegt der Ordner `famulus` nicht auf `volume1` (der Name hängt vom Volume ab, z. B. `volume2`), ersetze
  `/volume1/famulus` überall durch deinen Pfad (Suchen und Ersetzen, 6 Stellen). Den Pfad zeigt die Dateistation:
  Rechtsklick auf den Ordner → Eigenschaften. Auch den Projektpfad in Abschnitt 3 entsprechend anpassen.
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
Findest du ihn dort nicht, öffne im selben Fenster den Reiter **Terminal** → *Erstellen* und gib ein:
`cat /data/documents/.einrichtungscode`. Der Code hat die Form `ABCD-EFGH-JKLM`; die Datei verschwindet nach der Einrichtung.

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

**Zugriff von unterwegs:** Darunter fragt der Assistent „Wie erreichen Sie Famulus DMS?“. Bei **Auch von unterwegs (VPN)**
wählst du Tailscale, WireGuard in der FRITZ!Box oder ein anderes VPN. Der Assistent zeigt eine Kurzanleitung und nimmt
die Adresse der NAS im VPN gleich mit ins Zertifikat auf. Das VPN selbst richtest du außerhalb von Famulus DMS ein
(Abschnitt 8.1).

**Erlaubte Namen:** Rechnernamen bestehen aus Buchstaben, Ziffern und Bindestrich. Ein Unterstrich (`schneidt_ds`) ist
nicht erlaubt; benenne die NAS dann um (Systemsteuerung → Info-Center → Allgemein → Servername) oder trage die
IP-Adresse ein (im Router fest vergeben). Namen aus dem Internet (`example.com`) werden abgelehnt, für Zugriff von außen
siehe Abschnitt 8.

**Namen ohne Punkt** (z. B. `schneidt-ds`) erfordern eine neue Zertifizierungsstelle. Am Ende der Einrichtung erscheint
dann der Schritt „Einrichtung abgeschlossen“. Drücke **„Seite neu laden“** und bestätige die Browser-Warnung noch einmal;
danach meldest du dich an. Bereits eingerichtete Geräte installieren die neue Zertifizierungsstelle über die
Zertifikat-Hilfe (siehe unten).

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

1. In Famulus DMS unter **Diagnose** neben der Versionsnummer auf **Auf Updates prüfen** klicken. Die Anwendung fragt
   dann (nur auf Knopfdruck) bei GitHub nach der neuesten Version und nennt die Versionsnummer und das Image. (Wer
   Abschnitt 6.1 eingerichtet hat, aktualisiert hier direkt mit **Jetzt aktualisieren** und kann die Schritte 2 bis 6 überspringen.)
2. Eine Sicherung anlegen (siehe oben).
3. Container Manager → **Projekt → homedms** → **Stopp**.
4. Die Compose-Datei bearbeiten und bei **allen** Zeilen mit `ghcr.io/sschneidt/famulus-dms:` die Versionsnummer
   eintragen, z. B. `ghcr.io/sschneidt/famulus-dms:0.2.4`.
5. Speichern und **Erstellen** (englisch: *Build*), danach **Starten**. Weil dieses Image lokal noch nicht existiert,
   lädt es der Container Manager herunter. Datenbankänderungen laufen beim Start automatisch.
6. Unter **Diagnose** prüfen, dass die neue Version angezeigt wird. Was sich geändert hat, steht im
   [Änderungsprotokoll](../CHANGELOG.md).

> **Warum nicht einfach bei `latest` bleiben?** Der Container Manager behält ein schon geladenes Image mit dem Namen
> `latest` und holt beim Erstellen keine neuere Fassung. Eine feste Versionsnummer, die du bei jedem Update änderst,
> ist deshalb zuverlässiger. Wer trotzdem bei `latest` bleibt, muss vor dem Erstellen das alte Image unter
> *Image* entfernen (das Projekt vorher stoppen).

Die Prüfung geht nur, wenn die NAS ins Internet kommt. Abschalten kannst du sie, indem du beim Dienst `app-api` unter
`environment` die Zeile `UPDATE_CHECK_URL: ""` ergänzt.

### 6.1 Aktualisieren aus der Anwendung (Aufgabe im Aufgabenplaner)

Wer nicht jedes Mal die Compose-Datei bearbeiten möchte, kann die Aktualisierung aus Famulus DMS heraus auslösen. Dann
erscheint unter **Diagnose → Auf Updates prüfen**, sobald es eine neuere Version gibt, zusätzlich der Knopf
**Jetzt aktualisieren**. Eingerichtet wird das einmalig mit einer Aufgabe im DSM-Aufgabenplaner.

**Wie das funktioniert und warum es sicher ist:** Famulus DMS bekommt **keinen** Zugriff auf Docker, denn wer die
Anwendung übernähme, könnte sonst die ganze NAS übernehmen. Beim Klick sichert die Anwendung die Datenbank und legt nur
eine kleine Datei `update-request.txt` mit der Versionsnummer in den Sicherungsordner. Ein kleines Skript, das **du**
als Aufgabe laufen lässt, schaut jede Minute dort nach. Es nimmt aus der Datei ausschließlich eine Versionsnummer der
Form `1.2.3` und lädt nur dieses eine Image (`ghcr.io/sschneidt/famulus-dms:<Version>`). Dann trägt es die Version in
der Compose-Datei ein (die alte bleibt als `docker-compose.yml.vorher` liegen), erstellt `app-api` und `app-worker` neu
und wartet, bis die neue Version gesund meldet. Meldet sie sich nicht, wird die alte Compose-Datei zurückgespielt und
die alte Version läuft wieder; die Datenbanksicherung von vor dem Update liegt im Sicherungsordner.

**Einrichten:**

1. Voraussetzung ist, dass im Projekt eine **feste Versionsnummer** im Image steht (Abschnitt 6, Schritt 4), nicht
   `latest`.
2. Das Skript herunterladen:
   [update-agent.sh](https://github.com/sschneidt/famulus-dms/releases/latest/download/update-agent.sh). Lege es mit
   *File Station* in den Ordner `famulus` (also `/volume1/famulus/update-agent.sh`; liegt dein Ordner auf `volume2`,
   entsprechend dort), **nicht** in `documents`, `scan` oder `backups`. Diese Ordner sieht die Anwendung, und das Skript
   läuft mit hohen Rechten.
3. DSM → **Systemsteuerung → Aufgabenplaner → Erstellen → Geplante Aufgabe → Benutzerdefiniertes Skript**.
4. Reiter **Allgemein**: Name `Famulus DMS aktualisieren`, Benutzer **root**.
5. Reiter **Zeitplan**: *Täglich*, *Erste Ausführungszeit* `00:00`, *Häufigkeit* **Alle 1 Minute**, *Letzte
   Ausführungszeit* `23:59`.
6. Reiter **Aufgabeneinstellungen**, Feld *Benutzerdefiniertes Skript*:

   ```bash
   UPDATE_DIR=/volume1/famulus/backups sh /volume1/famulus/update-agent.sh
   ```

   Anpassen: `UPDATE_DIR` ist der Sicherungsordner aus der Compose-Datei (`BACKUP_HOST_PATH`). Meldet das Skript später
   „Compose-Datei nicht gefunden“, ergänze davor `COMPOSE_FILE=/volume1/docker/homedms/docker-compose.yml` mit dem Pfad,
   unter dem das Projekt im Container Manager liegt.
7. **OK** und die Aufgabe aktivieren. Nach etwa einer Minute erkennt Famulus DMS das Skript: Unter **Diagnose → Auf
   Updates prüfen** erscheint bei einer neueren Version der Knopf **Jetzt aktualisieren**.

**Ablauf beim Aktualisieren:** Klick auf **Jetzt aktualisieren**, Bestätigen, dann zeigt die Seite den Fortschritt
(Herunterladen, Neustart, Warten auf die neue Version). Famulus DMS ist dabei etwa eine Minute nicht erreichbar. Zum
Schluss erscheint **Seite neu laden**. Ein Update, das nicht anläuft, zeigt die Seite als fehlgeschlagen an, mit dem
Hinweis des Skripts.

Beachte: Das Skript tauscht nur die Versionsnummer des Famulus-DMS-Images aus. Ändert eine neue Version die Compose-Datei
selbst (steht dann im [Änderungsprotokoll](../CHANGELOG.md)), musst du das wie bisher von Hand einarbeiten. Wer die
Aufgabe nicht mehr möchte, deaktiviert sie im Aufgabenplaner; Famulus DMS zeigt den Knopf dann nach wenigen Minuten
nicht mehr an.

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

## 8. Zugriff von unterwegs

Im Heimnetz genügt das eingebaute HTTPS. Von unterwegs (Dokumente ansehen oder hochladen) gibt es zwei Wege:

- **8.1 VPN** (empfohlen): Famulus DMS bleibt im Internet unsichtbar. Du brauchst weder eine Domain noch ein
  Webdienstportal bzw. einen Reverse-Proxy noch ein Let's-Encrypt-Zertifikat noch eine Portfreigabe für Famulus DMS.
- **8.2 Direkt über das Internet** mit eigener Domain, Let's-Encrypt-Zertifikat und dem DSM-Reverse-Proxy.

### 8.1 Zugriff über VPN

An Famulus DMS ändert sich nichts: Das Handy kommt über den Tunnel ins Heimnetz und ruft `https://<nas>:8443` auf wie zu
Hause. Welche Variante passt, hängt von deiner Ausstattung ab:

| Variante | Aufwand | Passt, wenn |
|---|---|---|
| **Tailscale** auf der NAS | am geringsten | Es gibt keine Portfreigabe oder keine feste Adresse, oder der Anbieter blockiert eingehende Verbindungen (CGNAT). |
| **WireGuard in der FRITZ!Box** | gering | Du hast eine FRITZ!Box. Das Handy sieht das ganze Heimnetz, auf der NAS ist nichts zu installieren. |
| **Synology VPN Server** (OpenVPN) | mittel | Alles soll auf der NAS laufen. Im Router ist eine Portfreigabe nötig. |

- **Tailscale:** Das Paket für die NAS (`.spk`) gibt es auf tailscale.com und wird im Paket-Zentrum manuell installiert.
  Auf dem Handy die Tailscale-App mit demselben Konto anmelden. Die Tailscale-Adresse der NAS (`100.x.y.z` oder
  `<name>.ts.net`) steht in der App.
- **FRITZ!Box:** Heimnetz → Netzwerk → Netzwerkeinstellungen → WireGuard, Verbindung anlegen und den QR-Code in der
  WireGuard-App scannen. Mit aktivem Tunnel gilt die normale Heimnetz-Adresse der NAS.

**Das Zertifikat muss zur Adresse passen.** Ruft das Handy die NAS im VPN unter einer anderen Adresse auf als im Heimnetz,
warnt der Browser. Trage alle Adressen in der Compose-Datei bei `TLS_HOSTNAMES` ein, durch Komma getrennt, und erstelle das
Projekt neu (oder trage sie schon bei der Ersteinrichtung ein, siehe Abschnitt 4):

```yaml
      TLS_HOSTNAMES: "192.168.1.10, 100.101.102.103, schneidt-ds.tail1234.ts.net"
```

Tailscale-Adressen (`100.64.0.0/10`, `*.ts.net`) erlaubt die eigene Zertifizierungsstelle. Die Seite *Diagnose* zeigt,
welche aufgerufenen Adressen das Zertifikat noch nicht abdeckt. Die Zertifizierungsstelle installierst du am Handy
einmalig über `http://<nas-adresse>:8000/zertifikat`, mit eingeschaltetem Tunnel oder im WLAN.

Die Zwei-Faktor-Anmeldung lohnt sich auch hier, falls ein Handy verloren geht.

### 8.2 Direkt über das Internet (Reverse-Proxy mit eigener Domain)

Nimm diesen Weg nur, wenn ein VPN nicht in Frage kommt. Das ist ein Zugriff über das offene Internet.

#### Voraussetzungen

- Ein Domainname, der auf deinen Anschluss zeigt: eigene Domain oder DDNS (Systemsteuerung → Externer Zugriff →
  DDNS, z. B. `name.synology.me`).
- Im Router eine Portweiterleitung **443 → NAS, Port 443** (nur diesen Port, **nicht** 8000 oder 8443).
- Ein Let's-Encrypt-Zertifikat für diesen Namen (Systemsteuerung → Sicherheit → Zertifikat → Hinzufügen).

#### Compose-Datei anpassen

Projekt `homedms` bearbeiten und beim Dienst `app-api` drei Dinge ändern, danach das Projekt neu erstellen
(die Daten bleiben erhalten):

```yaml
      TLS_MODE: off                  # statt auto: Famulus DMS spricht nur HTTP, der Proxy macht HTTPS
      FORWARDED_ALLOW_IPS: "*"       # neu: vertraut den Weiterleitungs-Headern des Proxys
    ports:
      - "127.0.0.1:8000:8000"        # nur lokal erreichbar; die Zeile mit 8443 löschen
```

- Ohne `FORWARDED_ALLOW_IPS` sieht Famulus DMS hinter dem Proxy weder `https` noch die echte Adresse des Aufrufers. Das
  Login-Cookie bekäme nicht das Secure-Flag, und die Sperre nach Fehlversuchen je Gerät würde alle Aufrufer von außen
  als ein einziges Gerät zählen.
- Der Port nur auf `127.0.0.1` sorgt dafür, dass niemand am Proxy vorbei an die Anwendung kommt. Setze
  `FORWARDED_ALLOW_IPS: "*"` nie, wenn der Port auch im Netz offen ist.
- Mit `TLS_MODE: off` entfallen die eigene Zertifizierungsstelle und die Seite `/zertifikat`. Auch im Heimnetz rufst du
  Famulus DMS dann über den Domainnamen auf (ein Eintrag im Router oder DNS, der den Namen auf die NAS-Adresse
  auflöst, vermeidet den Umweg über das Internet).

#### Reverse-Proxy-Regel anlegen

Systemsteuerung → Anmeldeportal → Erweitert → Reverse-Proxy → Erstellen:

| | |
|---|---|
| Quelle | Protokoll **HTTPS**, Hostname `famulus.deinedomain.de`, Port **443** |
| Ziel | Protokoll **HTTP**, Hostname `localhost`, Port **8000** |

Danach unter Systemsteuerung → Sicherheit → Zertifikat → **Konfigurieren** der Regel das Let's-Encrypt-Zertifikat zuweisen.
Bei der Regel (Bearbeiten → Erweitert) kannst du die Zeitüberschreitungen erhöhen, wenn große Uploads über eine
langsame Mobilverbindung abbrechen. Teste den Upload einer großen PDF-Datei von außen (Mobilfunk, nicht WLAN).

#### Absichern (wichtig, bevor du den Port freigibst)

Von außen ist die Anmeldeseite für jeden im Internet erreichbar. Das sensible Material (deine Dokumente) schützen dann
nur die Anmeldung und die Aktualität der Software:

1. **Zwei-Faktor-Anmeldung für jedes Konto** einschalten (Famulus DMS → Konto). Sie ist noch nicht erzwingbar; die
   Benutzerliste markiert Admins ohne Zwei-Faktor-Anmeldung.
2. **Lange, einmalige Passwörter** (Passwortmanager).
3. Die Sperre nach Fehlversuchen ist eingebaut (5 Fehlversuche je Konto, 20 je Gerät in 15 Minuten).
4. DSM selbst absichern: Systemsteuerung → Sicherheit → **Automatische Blockierung** und Firewall (nur Ports 443 und die
   Dienste, die du brauchst). Leite im Router nur Port 443 weiter, damit die DSM-Oberfläche (Port 5001) von außen nicht
   erreichbar ist.
5. Regelmäßig aktualisieren (Abschnitt 6) und DSM-Updates einspielen.

## Problemlösung

| Problem | Lösung |
|---|---|
| Projekt lässt sich nicht erstellen | Projektname `homedms`, Pfad `/volume1/famulus/app` und die Ordner `documents`, `scan`, `backups` müssen existieren |
| Seite nicht erreichbar | Läuft der Container `homedms-app-api-1`? Ports 8000/8443 und Firewall prüfen |
| Zertifikatswarnung | Beim ersten Mal normal; danach Anleitung unter `http://<nas>:8000/zertifikat`. Warnt der Browser weiter, fehlt die Adresse im Zertifikat (siehe Abschnitt 4) |
| „Failed to fetch“ auf fast jeder Seite direkt nach der Einrichtung | Das Zertifikat wurde während der Einrichtung neu ausgestellt. Seite neu laden (`Strg+F5`) bzw. den Tab schließen und neu öffnen, die Ausnahme bestätigen. Hilft das nicht, die Zertifizierungsstelle über `http://<nas>:8000/zertifikat` neu installieren |
| Einrichtung lehnt den Namen ab | Nur Buchstaben, Ziffern und Bindestrich, kein Unterstrich; nur Heimnetz-Namen oder -Adressen (siehe Abschnitt 4) |
| Einrichtungscode nicht auffindbar | Container → `homedms-app-api-1` → Details → Terminal: `cat /data/documents/.einrichtungscode` (Abschnitt 3) |
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
