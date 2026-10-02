# API-Endpunktliste: HomeDMS

Stand: 10.09.2026 · Version 0.1 · Basis: `Anforderungsdokument.md` und `Datenmodell.md`

REST-API auf Basis von FastAPI, Base-Path `/api/v1`. Alle Endpunkte sind implizit auf den Tenant des angemeldeten Nutzers beschränkt (`tenant_id` kommt aus dem JWT, nicht aus der URL) – vermeidet versehentliches Cross-Tenant-Routing über die API selbst, zusätzlich zur DB-seitigen Row-Level-Security (Datenmodell 1).

## 1. Konventionen

- **Auth:** `Authorization: Bearer <access_token>` (JWT, siehe Datenmodell 4). Access-Token kurzlebig (~15 Min), Refresh über eigenen Endpunkt.
- **Pagination:** Listen-Endpunkte akzeptieren `?page=&page_size=` (Default 25, Max 100) und antworten mit `{"items": [...], "page": …, "page_size": …, "total": …}`. Bei < 50 Dokumenten/Monat reicht einfaches Offset-Paging, keine Cursor-Komplexität nötig.
- **Filterung/Sortierung** (wo sinnvoll): Query-Parameter, z. B. `?category_id=&tag=&status=&date_from=&date_to=&sort=created_at:desc`.
- **Volltextsuche:** Parameter `q` auf `/documents` – wird intern an Meilisearch delegiert, Ergebnis bleibt aber ein normales Dokumenten-Array (kein separates Such-Response-Format).
- **Fehlerformat:** `{"error": {"code": "category_not_found", "message": "…", "details": {...}}}` plus passender HTTP-Status.
- **Rechte-Durchsetzung:** Jeder Dokument-lesende/schreibende Endpunkt wendet das Sichtbarkeitsmodell aus Datenmodell 3.6 an (Admin/Owner/CategoryAccess/DocumentAccessOverride) – unzugängliche Dokumente werden aus Listen gefiltert, ein direkter Zugriff per ID liefert `403`.
- **Chat-Tool-Aufrufe sind keine eigene Implementierung:** Die Function-/Tool-Calling-Schnittstelle des Chat-Assistenten (Anforderungsdokument 4.3) ruft **dieselben** unten gelisteten Endpunkte auf (intern, mit den Rechten des Chat-Nutzers) – es gibt keine parallele Logik nur für den Chat.

## 2. Auth & Einrichtung

| Methode | Pfad | Zweck | Rolle |
|---|---|---|---|
| POST | `/auth/login` | Login mit E-Mail/Passwort, liefert Access- + Refresh-Token | öffentlich |
| POST | `/auth/refresh` | Neues Access-Token gegen gültiges Refresh-Token | öffentlich (Token-Besitz) |
| POST | `/auth/logout` | Refresh-Token widerrufen | angemeldet |
| GET | `/auth/me` | Eigenes Nutzerprofil + Rolle + Tenant-Info | angemeldet |
| POST | `/setup/bootstrap` | Einmaliger Ersteinrichtungs-Schritt: legt Tenant + ersten Admin-User an (Einrichtungsassistent, Anforderungsdokument 4.7) | öffentlich, nur wenn noch kein Tenant existiert |
| GET | `/setup/status` | Fortschritt der Ersteinrichtung (u. a. Ollama-Modell-Download-Status) | angemeldet (Admin) |

## 3. Nutzer & Haushalt

| Methode | Pfad | Zweck | Rolle |
|---|---|---|---|
| GET | `/tenant` | Aktuelle Haushaltseinstellungen (Name, Sprache) | angemeldet |
| PATCH | `/tenant` | Haushaltseinstellungen ändern | Admin |
| GET | `/users` | Haushaltsmitglieder auflisten | angemeldet |
| POST | `/users` | Neues Mitglied anlegen/einladen | Admin |
| GET | `/users/{id}` | Nutzerdetails | angemeldet |
| PATCH | `/users/{id}` | Rolle, Benachrichtigungskanäle etc. ändern | Admin oder eigenes Profil |
| DELETE | `/users/{id}` | Mitglied entfernen | Admin |
| PUT | `/users/{id}/password` | Passwort ändern/zurücksetzen | Admin oder eigenes Profil |

## 4. Kategorien, Tags & Rechte

| Methode | Pfad | Zweck | Rolle |
|---|---|---|---|
| GET | `/categories` | Kategorien des Haushalts (inkl. `is_restricted`) | angemeldet |
| POST | `/categories` | Neue Kategorie anlegen | Admin (oder aus Feedback-Loop/Chat mit entsprechender Berechtigung) |
| PATCH | `/categories/{id}` | Umbenennen, Beschreibung ändern, `is_restricted` umschalten | Admin |
| DELETE | `/categories/{id}` | Löschen (nicht möglich für `is_system_default`, siehe Datenmodell 3.3) | Admin |
| GET | `/categories/{id}/access` | Sichtbarkeits-Allowlist einer restringierten Kategorie | Admin |
| PUT | `/categories/{id}/access` | Allowlist setzen (`CategoryAccess`-Einträge) | Admin |
| GET | `/tags` | Tags des Haushalts | angemeldet |
| POST | `/tags` | Tag anlegen | angemeldet |
| DELETE | `/tags/{id}` | Tag löschen | angemeldet (eigene) / Admin |

## 5. Dokumente

| Methode | Pfad | Zweck | Rolle |
|---|---|---|---|
| GET | `/documents` | Liste/Suche/Filter (siehe Konventionen), respektiert Sichtbarkeitsmodell, zeigt standardmäßig keine gelöschten Dokumente | angemeldet |
| POST | `/documents` | Neues Dokument anlegen (Multipart-Upload: Datei(en) + optionale Metadaten) – deckt Foto-Import, manuellen Upload ab | angemeldet |
| GET | `/documents/needs-review` | Feedback-Loop-Warteschlange (`classification_status = needs_review`) | angemeldet (gefiltert auf sichtbare Dokumente) |
| GET | `/documents/trash` | Papierkorb: Dokumente mit gesetztem `deleted_at` (siehe Datenmodell 3.5), max. 30 Tage sichtbar | angemeldet + Sichtbarkeit |
| GET | `/documents/{id}` | Dokumentdetails inkl. Metadaten, Kategorie, Tags | angemeldet + Sichtbarkeit |
| PATCH | `/documents/{id}` | Titel, Tags, Original-Tracking-Felder etc. ändern | angemeldet + Sichtbarkeit/Edit-Recht |
| DELETE | `/documents/{id}` | Soft-Delete: setzt `deleted_at`, Dokument wandert in den Papierkorb (Datenmodell 3.5) | angemeldet + Edit-Recht |
| POST | `/documents/{id}/restore` | Aus dem Papierkorb wiederherstellen (`deleted_at` zurücksetzen) | angemeldet + Edit-Recht |
| GET | `/documents/{id}/download` | Original-Datei(en) herunterladen | angemeldet + Sichtbarkeit |
| POST | `/documents/{id}/pages` | Seiten (PDF/Bilder) hinzufügen, optional `position` (vor Seite n) – umgesetzt 02.10.2026: ein mehrseitiges Dokument ist **eine PDF-Datei**; mehrere Dateien beim Hochladen (`POST /documents` mit mehreren `file`-Teilen) werden ebenfalls zu einer PDF zusammengefasst | angemeldet + Edit-Recht |
| DELETE | `/documents/{id}/pages/{n}` | Einzelne Seite entfernen (die letzte nicht) | angemeldet + Edit-Recht |
| PUT | `/documents/{id}/pages/order` | Seiten umsortieren (`{"order": [2, 1, 3]}`) | angemeldet + Edit-Recht |
| GET | `/documents/{id}/pages/{n}/thumbnail` | Vorschaubild einer Seite (PNG) | angemeldet + Sichtbarkeit |
| POST | `/documents/{id}/category` | Kategorie manuell setzen/korrigieren (Feedback-Loop-Bestätigung) → erzeugt `ClassificationEvent` + neues `CategoryExemplar` | angemeldet + Edit-Recht |
| GET | `/documents/{id}/classification-history` | Verlauf aller `ClassificationEvent`-Einträge | angemeldet + Sichtbarkeit |
| POST | `/documents/bulk-reclassify` | Massen-Umkategorisierung über Filterkriterien (Chat-Tool-Funktion, siehe 1.) | angemeldet + Edit-Recht auf betroffene Dokumente |
| GET | `/documents/{id}/access` | Dokument-Zugriffs-Ausnahmen (`DocumentAccessOverride`) | Admin/Owner |
| PUT | `/documents/{id}/access` | Zugriffs-Ausnahmen setzen | Admin/Owner |

## 6. Wiedervorlage / Termine

| Methode | Pfad | Zweck | Rolle |
|---|---|---|---|
| GET | `/wiedervorlagen` | Haushaltsweite Übersicht (Filter: `status`, `due_before`, `assigned_user_id`) – Grundlage für die Termin-Übersicht (Anforderungsdokument 4.4a) | angemeldet + Sichtbarkeit des jeweiligen Dokuments |
| GET | `/documents/{id}/wiedervorlagen` | Wiedervorlagen eines Dokuments | angemeldet + Sichtbarkeit |
| POST | `/documents/{id}/wiedervorlagen` | Neue Wiedervorlage manuell anlegen | angemeldet + Edit-Recht |
| PATCH | `/wiedervorlagen/{id}` | Termin/Notiz/Zuweisung ändern, oder KI-Vorschlag korrigieren | angemeldet + Edit-Recht |
| POST | `/wiedervorlagen/{id}/confirm` | KI-Vorschlag (`status = vorgeschlagen`) bestätigen → `offen` | angemeldet + Edit-Recht |
| POST | `/wiedervorlagen/{id}/reject` | KI-Vorschlag ablehnen → `verworfen` | angemeldet + Edit-Recht |
| POST | `/wiedervorlagen/{id}/complete` | Als erledigt markieren (erzeugt bei Wiederkehr automatisch die nächste Instanz) | angemeldet + Edit-Recht |
| DELETE | `/wiedervorlagen/{id}` | Löschen | angemeldet + Edit-Recht |

## 7. Aufbewahrungsregeln

| Methode | Pfad | Zweck | Rolle |
|---|---|---|---|
| GET | `/retention-rules` | Regeln des Haushalts | Admin |
| POST | `/retention-rules` | Neue Regel anlegen | Admin |
| PATCH | `/retention-rules/{id}` | Regel ändern | Admin |
| DELETE | `/retention-rules/{id}` | Regel löschen | Admin |

## 8. Import-Quellen

| Methode | Pfad | Zweck | Rolle |
|---|---|---|---|
| GET | `/import-sources` | Konfigurierte Scan-Ordner/Agenten | Admin |
| POST | `/import-sources` | Neue Quelle anlegen (NAS-Ordner oder Client-Agent-Token) | Admin |
| PATCH | `/import-sources/{id}` | Konfiguration ändern, aktivieren/deaktivieren | Admin |
| DELETE | `/import-sources/{id}` | Quelle entfernen | Admin |
| POST | `/import-sources/{id}/scan-now` | Ordner sofort statt beim nächsten Poll-Intervall prüfen | Admin |

## 9. Benachrichtigungen

| Methode | Pfad | Zweck | Rolle |
|---|---|---|---|
| GET | `/notifications` | Eigene Benachrichtigungen (Filter: `status`) | angemeldet |
| POST | `/notifications/{id}/read` | Als gelesen markieren | angemeldet (eigene) |
| POST | `/push-subscriptions` | Web-Push-Endpoint registrieren | angemeldet |
| DELETE | `/push-subscriptions/{id}` | Push-Abo entfernen | angemeldet (eigene) |

## 10. KI-Konfiguration

| Methode | Pfad | Zweck | Rolle |
|---|---|---|---|
| GET | `/ai-config` | Aktuelle KI-Einstellungen (Provider, Modelle, `caution_level`) | Admin |
| PATCH | `/ai-config` | Provider wechseln (lokal/extern), `caution_level` anpassen, externen API-Key hinterlegen | Admin |
| GET | `/ai-config/model-status` | Download-/Ladezustand des lokalen Ollama-Modells | Admin |

## 11. KI-Chat-Assistent

| Methode | Pfad | Zweck | Rolle |
|---|---|---|---|
| GET | `/chat/sessions` | Eigene Chat-Sessions (dokumentbezogen + global) | angemeldet |
| POST | `/chat/sessions` | Neue Session starten (`scope_document_id` optional) | angemeldet |
| GET | `/chat/sessions/{id}/messages` | Nachrichtenverlauf | angemeldet (eigene Session) |
| POST | `/chat/sessions/{id}/messages` | Nachricht senden; Antwort inkl. ausgeführter Tool-Calls (siehe 1.) | angemeldet (eigene Session) |
| DELETE | `/chat/sessions/{id}` | Session löschen | angemeldet (eigene Session) |

*Hinweis:* `POST /chat/sessions/{id}/messages` liefert die Antwort bevorzugt als Server-Sent-Events-Stream (bessere UX bei lokalem LLM mit spürbarer Latenz), alternativ als einfache synchrone JSON-Antwort als Fallback.

## 12. System

| Methode | Pfad | Zweck | Rolle |
|---|---|---|---|
| GET | `/health` | Liveness/Readiness (für Docker Healthcheck) | öffentlich |
| GET | `/version` | Backend-/Schema-Version (u. a. für Update-Diagnose, Anforderungsdokument 4.7) | angemeldet |

## 13. Offene Punkte für die nächste Iteration

- Exaktes OpenAPI-Schema (Request-/Response-Bodies, Validierungsregeln) – FastAPI generiert das Grundgerüst automatisch aus den Pydantic-Modellen, die noch aus dem Datenmodell abzuleiten sind.
- Soft-Delete-Verhalten ist entschieden (Papierkorb, 30 Tage, `POST /documents/{id}/restore`, siehe Datenmodell 3.5); genauer Ablauf des endgültigen Lösch-Jobs folgt bei der Umsetzung.
- Rate-Limiting/Anti-Abuse für `/auth/login` (Brute-Force-Schutz), auch bei nur wenigen Nutzern sinnvoll.
- Genaues Streaming-Format für den Chat-Endpunkt (SSE-Event-Struktur, wie Tool-Call-Zwischenschritte dem Nutzer angezeigt werden).
- Ob `/documents` bei sehr vielen Filtern eine POST-Variante mit Body statt Query-Parametern braucht (bei aktuellem Volumen nicht nötig).
