# Anforderungsdokument: HomeDMS
### Dokumentenmanagementsystem für Privathaushalte

Stand: 21.09.2026 · Version 0.1 (Ergebnis des Anforderungs-Interviews)

---

## 1. Zielsetzung

HomeDMS reduziert die Anzahl physischer Papierdokumente in Privathaushalten durch automatisierten, KI-gestützten Import, Texterkennung, Klassifizierung und Ablage. Das System läuft selbst-hostet in einem Docker-Container auf einem Synology-NAS und ist über Web-Browser (PWA) sowie später optional über eine native App nutzbar. Mehrere Haushalte (Mandanten) mit jeweils mehreren Nutzern können dieselbe Instanz gemeinsam nutzen, mit strikter Datentrennung zwischen den Haushalten.

## 2. Architekturüberblick

- **Client-Server-Architektur** mit REST-API als zentrale Schnittstelle zwischen Backend und allen Clients (Web-UI, App, Scan-Agent).
- **Multi-Tenant-Modell:** Mandant = Haushalt. Ein Mandant hat mehrere Nutzer mit individuellen Rollen/Rechten. Daten sind strikt pro Mandant isoliert (kein Zugriff/Sichtbarkeit über Haushaltsgrenzen hinweg).
- **Deployment:** Docker-Container(-Stack) auf Synology-NAS (Mittelklasse, z. B. DS923+/DS1522+, x86, 8–32 GB RAM). Docker/Container Manager ist bereits vorhanden, ein Reverse Proxy mit Domain/TLS ist noch einzurichten (z. B. via Synology-eigenem Reverse Proxy oder Traefik/Caddy als Teil des Compose-Stacks).
- **Frontend:** Progressive Web App (PWA), responsive, installierbar auf Smartphone-Homescreen mit Kamera-Zugriff über Browser-API. Spätere Verpackung als native App (z. B. via Capacitor) ohne Neubau der UI möglich.
- **Skalierung/Volumen (Auslegungsgröße):** kleiner Umfang – unter 50 Dokumente/Monat, Gesamtbestand im Bereich wenige Tausend Dokumente.
- **Betriebsphilosophie:** Einfache Installation und Konfiguration ist ein explizites, hoch priorisiertes Ziel (siehe 4.7) – die interne Komplexität (mehrere Dienste, KI-Modelle, Datenbank) wird von der Anwendung selbst verwaltet, nicht dem Nutzer aufgebürdet.

## 3. Mandanten- und Rollenmodell

- Mandant (Haushalt) → Nutzer (Haushaltsmitglieder) → Dokumente.
- Rollenmodell **fein granular**: Sichtbarkeit ist pro Dokument bzw. pro Kategorie konfigurierbar (z. B. Kinder sehen nur eigene Dokumente wie Schule/Gesundheit, Eltern sehen alles). Empfehlung für V1: Basis-Rollen Admin (Haushalt verwalten, Nutzer/Kategorien anlegen) und Mitglied, ergänzt um eine Sichtbarkeits-/ACL-Ebene pro Dokument oder Kategorie.

## 4. Funktionale Anforderungen

### 4.1 Import-Wege
- **App → Foto:** Aufnahme über Smartphone-Kamera (PWA MediaDevices-API), inkl. automatischer Perspektivkorrektur/Zuschnitt des fotografierten Dokuments.
- **Upload bereits gescannter Dokumente** über Web-UI/App (Datei-Auswahl).
- **Scan-Ordner-Agent:** Überwachung eines Ordners und automatischer Import definierter Dateitypen. Unterstützt werden **beide** Varianten:
  - primär ein NAS-seitiger Ordner (Scanner/Multifunktionsgerät legt Scans direkt per SMB/FTP-Scan-to-Folder ab, Backend-Container überwacht diesen Ordner),
  - optional ein kleiner Client-Agent auf einem PC für Ordner, die nicht direkt vom NAS aus sichtbar sind.
- **Unterstützte Datei-Formate:** PDF (gescannt oder digital), JPG/HEIC (Foto-Import), TIFF/PNG (Multifunktionsdrucker-Scans), Office-Dokumente (Word/Excel) und E-Mails (.eml/.msg).

### 4.2 OCR
- Automatisches OCR im Hintergrund (asynchrone Verarbeitung/Queue, damit Import nicht blockiert).
- Engine: Tesseract, Sprachpakete Deutsch + Englisch als Primärsprachen; weitere Sprachen als nachrüstbare Module.

### 4.3 Klassifizierung & Kategorisierung (KI-gestützt, fester Bestandteil)
- Automatische Kategorie-Identifizierung und Klassifizierung ist **kein optionales Add-on, sondern fester Kernbestandteil** der Anwendung (nicht nur ein einfacher Regel-Fallback).
- Verarbeitungskette: OCR-Text → KI-basierte Kategorisierung/Klassifizierung → Vorschlag für Kategorie, Tags, relevante Metadaten (Absender, Datum, Betrag bei Rechnungen etc.).
- **Klarstellung Klassifikation vs. Extraktion:** Die zweistufige Ressourcenschonung (Stufe 1/Stufe 2 unten) gilt nur für die **Kategorie-Entscheidung**. Das Erkennen von Metadaten (Datum, Absender, Betrag) und insbesondere von Fristen/Terminen (4.4a) ist reine Textverständnis-Aufgabe und braucht **immer** einen LLM-Aufruf – unabhängig davon, ob die Kategorie schon über die schnelle Stufe 1 stand. Dieser Extraktions-Aufruf läuft für jedes Dokument einmal (asynchron, on-demand wie in 4.7 beschrieben); läuft ohnehin schon eine Stufe-2-Zweitmeinung zur Kategorie, wird die Extraktion in demselben Ollama-Aufruf mit erledigt, sonst als eigener, kleiner Aufruf. Bei dem geplanten Volumen (< 50 Dokumente/Monat) ist das ressourcentechnisch unkritisch – ein einzelner kurzer Ollama-Aufruf pro Dokument.
- **Kategorien-Set ist von Anfang an offen erweiterbar** (keine feste, geschlossene Liste) – neue Kategorien können jederzeit angelegt werden, auch direkt aus dem Feedback-Loop heraus.
- **Klassifizierungs-Workflow (Reihenfolge verbindlich), zweistufig, um Ollama nicht bei jedem Dokument bemühen zu müssen (siehe Ressourcenschema 4.7):**
  1. **Stufe 1 – Embedding-Klassifikator (schnell, kein LLM-Aufruf):** Der OCR-Text wird in einen Vektor (Embedding) umgewandelt und mit den bereits bestätigten Beispiel-Dokumenten ("Exemplare") jeder Kategorie verglichen (Nearest-Neighbor/Centroid). Ist die Ähnlichkeit zur besten Kategorie eindeutig hoch, wird die Kategorie **direkt automatisch zugewiesen** – kein manueller Schritt, keine KI-Modell-Inferenz nötig.
  2. **Stufe 2 – LLM-Zweitmeinung (Ollama, nur bei Bedarf):** Ist Stufe 1 uneindeutig (z. B. mehrere Kategorien ähnlich nah, oder eine neue Kategorie hat noch zu wenige Exemplare), bekommt das lokale KI-Modell den Dokumenttext plus die Liste aller Kategorien (inkl. Beschreibung) und liefert strukturiert Kategorie-Vorschlag, Tags, Metadaten und eine eigene Konfidenzangabe.
  3. Erreicht auch die LLM-Zweitmeinung nicht die nötige Konfidenz (oder keine Kategorie passt), wandert das Dokument in den **Feedback-Loop**: Ein Nutzer weist die Kategorie manuell zu oder legt bei Bedarf eine neue Kategorie an.
  4. Jede bestätigte Zuordnung (automatisch akzeptiert oder manuell korrigiert/neu angelegt) wird sofort als neues Exemplar für die betroffene Kategorie gespeichert – die Klassifikation verbessert sich dadurch **inkrementell und in Echtzeit**, ein separater Batch-Retrainingslauf ist für diesen Ansatz nicht nötig.
- **Konfidenz-Schwellenwerte (Startwerte, in den Admin-Einstellungen als ein einfacher Regler "wie vorsichtig soll die KI sein" konfigurierbar, keine Einzelwerte von Hand nötig):**
  - Ähnlichkeit Stufe 1 ≥ 85 % (bzw. Abstand zur zweitbesten Kategorie ≥ 15 Punkte) → automatisch zuweisen, Stufe 2 wird übersprungen.
  - Ähnlichkeit Stufe 1 zwischen 65–85 % → Stufe 2 (LLM) zur Bestätigung; bei LLM-Konfidenz ≥ 80 % automatisch zuweisen, sonst Feedback-Loop.
  - Ähnlichkeit Stufe 1 < 65 % oder Kategorie hat noch keine/zu wenige Exemplare (Richtwert < 5) → direkt Stufe 2; bei LLM-Konfidenz ≥ 80 % automatisch zuweisen, sonst Feedback-Loop.
  - Diese Werte sind bewusst nur Startwerte und müssen an echten Testdokumenten kalibriert werden (siehe Abschnitt 7).
- **Vektor-Speicherung:** Embeddings der Exemplare werden über die `pgvector`-Erweiterung direkt in PostgreSQL gespeichert – kein zusätzlicher Vektordatenbank-Dienst nötig (passt zur Anforderung "möglichst wenige Container", Abschnitt 4.7).
- **Basis-Kategorien-Set** (bestätigt als Startpunkt, frei umbenennbar/erweiterbar/löschbar über den Einrichtungsassistenten bzw. später in den Einstellungen):
  Rechnungen · Verträge · Versicherungen · Bank & Finanzen · Steuern · Gesundheit & Medizinisches · Behörden & Amtliches · Wohnen & Nebenkosten · Fahrzeug · Arbeit & Gehalt · Bildung · Garantien & Kaufbelege · Sonstiges.
  "Sonstiges" ist dabei eine echte, bestätigte Kategorie für Dokumente, die die KI sicher keiner spezifischeren Kategorie zuordnen kann – zu unterscheiden vom Feedback-Loop-Status "zu prüfen", der keine Kategorie ist, sondern die Warteschlange für unsichere Fälle.
- **KI-Chat-Assistent (vollwertiger Bibliotheks-Assistent):** Chat-Schnittstelle, die sowohl auf Dokumentebene als auch global über den gesamten Bestand arbeitet, u. a.:
  - gezielte Fragen beantworten ("Zeig mir alle Rechnungen von 2025"),
  - einzelne Dokumente umklassifizieren/umkategorisieren,
  - Massen-Umkategorisierung über Filterkriterien (z. B. "Kategorisiere alle Dokumente von Firma X als Versicherung"),
  - dafür nötig: Function-/Tool-Calling des Chat-Modells auf Such-, Filter- und Änderungsfunktionen der API.
- **KI-Betriebsmodell:** lokal bevorzugt (Ollama mit kleinem quantisiertem Modell, passend zur NAS-Hardware), optional konfigurierbar mit externer KI-API (eigener API-Key), um bei Bedarf höhere Antwortqualität zu erhalten. Modul so bauen, dass das Klassifikations-/Chat-Backend austauschbar ist (lokal ↔ extern).

### 4.4 Ablage & Suche
- Kombiniertes Ablagemodell: **automatische Ordnerstruktur nach Kategorie/Jahr** (nachvollziehbar, z. B. auch direkt über Synology File Station einsehbar) **plus** freie Tags und Volltextsuche für flexible Filterung.
- Volltextsuche über OCR-Text mit **Tippfehler-Toleranz** – empfohlen: Meilisearch als leichtgewichtiger Zusatzdienst (Alternative: PostgreSQL + `pg_trgm`, geringere Fehlertoleranz, kein Zusatzdienst).
- Original-Tracking: Metadatenfeld "Original vorhanden: ja/nein/Aufbewahrungsort" pro Dokument (unabhängig von Terminen, siehe 4.4a).
- **Löschen (Soft-Delete):** Gelöschte Dokumente landen zunächst 30 Tage lang in einem wiederherstellbaren Papierkorb (`deleted_at`-Zeitstempel statt sofortigem Hard-Delete), erst danach entfernt ein Hintergrund-Job sie endgültig. Vermeidet versehentlichen, endgültigen Datenverlust bei einem Klick.

### 4.4a Wiedervorlage / Termine (generisches Erinnerungsfeature)
Verallgemeinerung der ursprünglichen Aufbewahrungsfrist-Erinnerung zu einem frei nutzbaren Termin-Feature, das die Aufbewahrungsfrist als einen Spezialfall miteinschließt.

- **Mehrere Wiedervorlagen pro Dokument** möglich (z. B. bei einem Vertrag: eine zur Kündigungsfrist, eine weitere zur jährlichen Preisprüfung).
- Jede Wiedervorlage hat einen **Termin (Datum)**, eine **Notiz** (was ist zu tun/warum) und optional eine **Zuweisung an ein bestimmtes Haushaltsmitglied** (Default: Dokument-Owner).
- **Wiederkehrend möglich** (z. B. jährlich, monatlich, freies Intervall): Nach Erledigung wird automatisch der nächste Termin angelegt.
- **Herkunft einer Wiedervorlage:**
  - **aus einer Aufbewahrungsregel** (`RetentionRule`, siehe Datenmodell) automatisch erzeugt, sobald Kategorie/Dokumentdatum bekannt sind,
  - **automatisch von der KI vorgeschlagen**, indem Fristen/Termine direkt aus dem Dokumententext erkannt werden (z. B. Kündigungsfrist in einem Vertrag) – Erweiterung der bestehenden KI-Extraktion (Dokumentdatum, Absender, Betrag). KI-Vorschläge landen zunächst im Status "vorgeschlagen" und müssen vom Nutzer bestätigt oder korrigiert werden, bevor sie aktiv sind,
  - **frei manuell** vom Nutzer angelegt.
- Fällige und anstehende Wiedervorlagen sind eine eigene Übersicht in der Oberfläche (nicht nur Benachrichtigung), damit man auch ohne aktiven Alarm nachsehen kann, was in nächster Zeit anfällt.

**KI-Fristenerkennung im Detail:**
- **Wann:** Läuft für jedes Dokument einmal, direkt im Rahmen des ohnehin nötigen Extraktions-Aufrufs (siehe Klarstellung in 4.3) – unabhängig davon, welche Kategorie zugewiesen wurde oder über welche Stufe. Es gibt **keine Kategorie-Filterliste**, die bestimmte Kategorien von vornherein ausschließt: Das Modell bekommt bei jedem Dokument die Chance, Fristen zu finden, liefert aber bei Dokumenten ohne relevante Termine schlicht eine leere Liste – einfacher und robuster als eine Pflege-Liste "welche Kategorie kann Fristen haben".
- **Was geliefert wird:** Pro erkannter Frist ein strukturierter Eintrag mit absolutem Datum (Umrechnung relativer Angaben wie "3 Monate vor Vertragsende" erfolgt durch das Modell selbst, unter Angabe von Dokumentdatum und heutigem Datum als Kontext), einer kurzen Bezeichnung (z. B. "Kündigungsfrist"), einem Konfidenzwert und dem **Original-Textausschnitt**, aus dem die Frist abgeleitet wurde (damit der Nutzer die KI-Aussage ohne erneutes Lesen des ganzen Dokuments prüfen kann). Optional ein Hinweis auf Wiederkehr (z. B. "jährliche Kündigungsfrist" → Vorschlag `recurrence = yearly`).
- **Vorschlags-Schwelle:** Konfidenz ≥ 50 % → wird als Wiedervorlage im Status "vorgeschlagen" angelegt; darunter wird der Fund verworfen (keine Benachrichtigungs-Flut durch sehr unsichere Treffer). Anders als bei der Kategorie-Klassifikation gibt es **keine automatische Übernahme ohne Bestätigung** – auch bei hoher Konfidenz –, da ein übersehener oder falscher Termin (z. B. eine verpasste Kündigungsfrist) höhere Konsequenzen hat als eine falsch zugeordnete Kategorie.
- **Keine Doppel-Vorschläge:** Existiert für ein Dokument bereits eine offene oder vorgeschlagene KI-Wiedervorlage, wird die Erkennung nicht automatisch wiederholt (z. B. bei erneuter OCR-Verarbeitung). Eine erneute Prüfung kann gezielt über den Chat-Assistenten angestoßen werden ("Schau nochmal nach Fristen in diesem Dokument"). Vom Nutzer abgelehnte Vorschläge ("verworfen") werden nicht automatisch erneut vorgeschlagen.

### 4.5 Benachrichtigungen
Kanäle: In-App-Benachrichtigungscenter, E-Mail (z. B. für fällige Wiedervorlagen) und Web-Push (PWA Service Worker). Auslöser u. a.: neues Dokument importiert, Wiedervorlage wird fällig, KI schlägt eine neue Wiedervorlage vor (braucht Bestätigung), Klassifikation unsicher/braucht Bestätigung.

### 4.6 Backup & Datensicherung
- Primär: Nutzung der Synology-eigenen Backup-Tools (z. B. Hyper Backup) auf das Docker-Volume mit Dokumenten + Datenbank.
- Ergänzend: eingebaute Export-Funktion für Einzeldokumente (Download durch Nutzer).

### 4.7 Installation, Einrichtung & Updates
**Priorität:** Minimaler Aufwand für den Nutzer bei Installation und Konfiguration – viele bestehende DMS-Lösungen dienen hier bewusst als negatives Vorbild (zu komplexe Einrichtung). Es wird **keine Funktionalität geopfert**, um das zu erreichen (volle Feature-Ausstattung inkl. Meilisearch und Ollama bleibt erhalten) – die Komplexität wird stattdessen intern gekapselt.

- **Start:** Ein `docker compose up` mit sinnvollen Defaults (wenige Werte in einer `.env`-Datei, z. B. Admin-Passwort, Ordnerpfade). Kein manuelles Editieren von Konfigurationsdateien für den Normalbetrieb.
- **Einrichtungsassistent:** Beim ersten Start öffnet sich in der Web-UI ein geführter Assistent, der alle inhaltlichen Erstkonfigurationsschritte per Klick abfragt – u. a. Admin-Konto, ersten Haushalt/Mandanten anlegen, Sprache, Speicherort/Scan-Ordner-Pfade, Basis-Kategorien-Set, Benachrichtigungskanäle. Ziel: so viel wie möglich läuft über den Assistenten, so wenig wie möglich erfordert händisches Konfigurieren.
- **KI-Modell-Bereitstellung:** Das Ollama-Modell wird beim ersten Start automatisch im Hintergrund heruntergeladen (kein manueller Schritt). Die Anwendung bleibt währenddessen nutzbar; Klassifikation/Chat werden aktiv, sobald der Download abgeschlossen ist. Der Assistent zeigt den Fortschritt an.
- **Ressourcenschema (Grundlage für "einfach & leichtgewichtig" trotz mehrerer Dienste):** Basis-Dienste (PostgreSQL, Meilisearch, Backend, Frontend) laufen dauerhaft, sind aber im Leerlauf zusammen deutlich unter 1 GB RAM und praktisch ohne CPU-Last. Rechenintensive Arbeit (OCR, KI-Klassifikation, Ollama-Inferenz) läuft **on-demand** über eine Job-Queue bzw. Ollamas automatisches Entladen inaktiver Modelle aus dem RAM (`keep_alive`) – Ressourcen werden nur bei tatsächlicher Nutzung beansprucht, dauerhaft hoher Verbrauch entsteht nicht.
- **Updates:** Erfolgen über einen einfachen Befehl (`docker compose pull && up`) bzw. optional Ein-Klick-Update über den Synology Container Manager. **Hartes Anforderungskriterium:** Bei Updates dürfen Daten, Archiv und Suchindex niemals verloren gehen. Dazu liegen Dokumente, Datenbank, Suchindex und heruntergeladene KI-Modelle in persistenten, benannten Docker-Volumes, die von Image-Updates unberührt bleiben; notwendige Datenbank-Schema-Migrationen laufen automatisch und verlustfrei beim Start der neuen Version.

## 5. Nicht-funktionale Anforderungen

- **Einfachheit der Installation & Konfiguration:** explizites, hoch priorisiertes Ziel. Erstinstallation über Docker Compose mit Defaults plus geführten Web-Einrichtungsassistenten (Details siehe 4.7); keine Feature-Abstriche zur Vereinfachung, stattdessen interne Kapselung der Komplexität (Ressourcenschema, automatischer Modell-Download, verlustfreie Update-Migrationen).
- **Sicherheit:** HTTPS zwingend für alle Verbindungen (API, Web-UI, App). Verschlüsselung der Dokumente "at rest" ist optional/spätere Ausbaustufe (z. B. über NAS-eigene Volume-Verschlüsselung), kein Hard-Requirement für V1.
- **Performance/Hardware-Rahmen:** Auslegung auf Mittelklasse-NAS (x86, 8–32 GB RAM) und kleines Dokumentvolumen (< 50/Monat). Lokale KI-Komponenten (OCR, Klassifikation, Ollama-Modell) müssen in diesem Rahmen praktikabel laufen (kleine, quantisierte Modelle statt großer LLMs).
- **Erweiterbarkeit:** Sprachpakete (OCR/Klassifikation), Klassifikations-Backend (lokal/extern) und Kategorien-Set müssen modular nachrüstbar sein, ohne Kernarchitektur zu ändern.
- **Multi-Tenancy:** Datenmodell von Beginn an mandantenfähig (Tenant-Ebene über allen Entitäten), da bestehende Open-Source-DMS (Paperless-ngx, Docspell, Mayan EDMS) dies nicht nativ unterstützen und eine Migration des Datenmodells nachträglich aufwendig wäre.

## 6. Technologie-Stack (Empfehlung, Basis-Zustimmung liegt vor)

| Bereich | Technologie | Begründung |
|---|---|---|
| Backend | Python (FastAPI) | Reifstes Ökosystem für OCR/KI-Integration, REST-API inkl. OpenAPI-Doku "out of the box", ressourcenschonend im Container |
| Datenbank | PostgreSQL (+ `pg_trgm` als Fallback, + `pgvector`-Erweiterung) | Robust, gute Multi-Tenant-Modellierung, native Volltextsuch-Option vorhanden, `pgvector` speichert Klassifikations-Exemplare ohne separaten Vektordatenbank-Dienst |
| Volltextsuche | Meilisearch | Leichtgewichtig, tippfehlertolerante Suche, geringer Zusatz-Ressourcenbedarf |
| Frontend | React oder Vue, als PWA | Eine Codebasis für Web + "App"-Erlebnis, später mit Capacitor in native Shell verpackbar |
| OCR | Tesseract (deu, eng, modular erweiterbar) | Bewährt, lokal, mehrsprachig |
| Klassifikation | Zweistufig: Embedding-Klassifikator (pgvector) als schneller Regelfall + Ollama-LLM als Zweitmeinung bei Unsicherheit, sonst Feedback-Loop | Erfüllt Anforderung "automatische Klassifizierung mit lokaler spezialisierter KI" als Kernfeature, hält Ollama-Last aber auf das Nötigste beschränkt (siehe 4.7) |
| KI-Chat/Reasoning | Ollama (lokal, kleines quantisiertes Modell) mit optionaler externer API als Alternative | Datenschutz-Präferenz (lokal) mit Ausweichoption für höhere Qualität |
| Reverse Proxy | Traefik/Caddy im Compose-Stack oder Synology Reverse Proxy | Noch einzurichten, da aktuell nicht vorhanden |
| Backup | Synology Hyper Backup + integrierte Export-Funktion | Nutzt vorhandene NAS-Infrastruktur, ergänzt um Nutzer-seitigen Einzel-Export |

## 7. Offene Punkte für die nächste Iteration

- Detailliertes Datenmodell (`Datenmodell.md`), REST-API-Endpunktliste (`API-Design.md`) und Docker-Compose-Entwurf (`Docker-Compose-Entwurf.md`) sind ausgearbeitet.
- Kalibrierung der vorgeschlagenen Konfidenz-Schwellenwerte (85 %/65 %/80 % Klassifikation, 50 % Fristenerkennung, siehe 4.3/4.4a) anhand echter Testdokumente, sobald verfügbar.
- Praxistauglichkeit der Fristenerkennung bei mehrsprachigen bzw. sprachlich uneindeutigen Formulierungen (4.4a) sowie Umgang mit Fehlvorschlägen über längere Nutzung hinweg.
- Auswahl des konkreten Embedding-Modells für Stufe 1 (mehrsprachig, klein genug für die NAS-Hardware) sowie Feinschliff des Basis-Kategorien-Sets (Abschnitt 4.3) in der Praxis (z. B. weitere Unterkategorien per Tags statt eigener Kategorie).
- Auswahl und Dimensionierung des lokalen KI-Modells für Ollama (Kompromiss Qualität vs. NAS-Ressourcen) inkl. Fallback-Verhalten bei Überlastung.
- Detailplanung Function-/Tool-Calling-Schnittstelle für den Chat-Assistenten (welche Aktionen darf er ausführen, Bestätigungs-Workflow vor destruktiven Massenänderungen).
- Feingranulares Rechte-/ACL-Modell ist im Detail gelöst (Datenmodell 3.6: Owner/Admin/`CategoryAccess`/`DocumentAccessOverride`).
- Reverse-Proxy-/TLS-Einrichtung: Empfehlung steht (Synologys eigener Reverse Proxy statt Zusatz-Container, siehe `Docker-Compose-Entwurf.md`); konkrete Domain-/Zertifikats-Schritte auf dem NAS des Nutzers stehen noch aus.
- Mobiler Foto-Import im Detail: Bibliothek für Kantenerkennung/Perspektivkorrektur, Mehrseiten-Scan-Workflow.
- Genaues Design des Einrichtungsassistenten (Schrittfolge, Pflicht- vs. optionale Felder, Validierungen).
- Job-Queue-Technologie ist entschieden und im Backend-Grundgerüst bereits verdrahtet (Procrastinate/PostgreSQL, kein Redis nötig, siehe `Docker-Compose-Entwurf.md` und `backend/homedms/worker.py`).
- ~~Konkrete Basis-Images/Dockerfiles für `app-api`/`app-worker`~~ – erledigt (`backend/Dockerfile`); Ressourcen-Limits pro Container und Image-Registry/Verteilung sind weiterhin offen (siehe `Docker-Compose-Entwurf.md`, Abschnitt 6).
- **Umsetzungsstand:** Implementierung läuft (siehe `backend/README.md` für den aktuellen Stand). Fertig: App-Grundgerüst, vollständiges Datenmodell als SQLAlchemy-Migration, Auth (JWT/Argon2), Einrichtung/Bootstrap, Kategorien-CRUD, Dokumente-Kernendpunkte (Upload/Liste/Detail/Soft-Delete/Download) inkl. Sichtbarkeitsmodell, OCR-Pipeline (PDF/Bild/E-Mail, siehe 4.2 - Office-Dokumente und .msg noch offen), Worker-Grundgerüst, Dockerfile für den vollen Compose-Stack, Testsuite (25 Tests). Offen: Klassifikation (Stufe 1+2), Fristenerkennung, Wiedervorlagen, Benachrichtigungen, KI-Chat-Assistent, Mehrseiten-Dokumente/Tags/Volltextsuche, Einrichtungsassistent im Detail, Frontend/PWA.
