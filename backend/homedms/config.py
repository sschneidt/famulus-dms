"""Zentrale Konfiguration. Env-Variablen spiegeln docker-compose.yml (Repo-Root)."""
import os
import secrets
import time
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

JWT_PLACEHOLDER = "dev-only-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_role: str = "api"  # "api" oder "worker" - siehe docker-compose.yml

    # Akzeptiert sowohl "postgresql://" als auch "postgresql+asyncpg://" - siehe
    # sqlalchemy_database_url/procrastinate_database_url unten fuer die normalisierten
    # Varianten, die die beiden unterschiedlichen Treiber (asyncpg vs. psycopg) brauchen.
    database_url: str = "postgresql://homedms:changeme@localhost:5432/homedms"

    # Leer = ohne Meilisearch: die Suche nutzt dann nur die Datenbank (Teilwort-Suche, ohne
    # Tippfehler-Toleranz) - z. B. fuer eine schlanke Installation ohne Docker.
    meilisearch_url: str = "http://localhost:7700"
    meilisearch_key: str = "changeme"

    ollama_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.2:3b"
    ollama_embedding_model: str = "nomic-embed-text"
    # Wartezeit auf eine Antwort des Sprachmodells. Auf einem NAS ohne GPU rechnet ein 3B-Modell
    # pro Dokument durchaus mehrere Minuten (v. a. beim ersten Laden ins RAM).
    ollama_timeout_seconds: int = 900
    # Tesseract-Sprachpakete fuer die Texterkennung (Anforderungsdokument 4.2), "+"-getrennt.
    # Standard, solange ein Admin auf der Seite "Sprachen" nichts anderes waehlt; dazu kommen immer
    # die Oberflaechensprachen der Personen. Fehlende Pakete laedt Famulus DMS selbst nach.
    ocr_languages: str = "deu+eng"
    # Eigener Ordner fuer Sprachpakete (mitgelieferte + nachinstallierte, core/ocr_languages.py).
    # Im Container fest "/data/tessdata" (eigenes Volume).
    tessdata_dir: str = "./data/tessdata"
    # Woher fehlende Sprachpakete kommen - offizielle Tesseract-Modelle ("fast": klein und schnell)
    ocr_download_url: str = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{code}.traineddata"
    # Pfad zu tesseract(.exe), falls nicht im PATH (Windows) - leer = automatisch suchen (runtime.py)
    tesseract_cmd: str = ""

    ai_caution_level: str = "normal"  # vorsichtig | normal | mutig, siehe Datenmodell 3.7 AIModelConfig

    # Wo Dokument-Dateien liegen. Im Container immer "/data/documents" (fester Mount-Punkt,
    # siehe docker-compose.yml); fuer lokale Entwicklung ohne Docker Default relativ zum cwd.
    documents_path: str = "./data/documents"
    # Ueberwachter Scan-Ordner (Anforderungsdokument 4.1). Im Container fest "/data/scan".
    scan_path: str = "./data/scan"
    # Nur zur Anzeige: wo der Scan-Ordner auf dem NAS/PC tatsaechlich liegt. Im Docker-Betrieb
    # setzt docker-compose.yml das aus SCAN_FOLDER_PATH (.env) - der Container selbst sieht nur
    # /data/scan. Leer = ohne Docker, dann ist scan_path selbst der echte Ordner.
    scan_host_path: str = ""
    scan_interval_cron: str = "* * * * *"  # jede Minute nachsehen
    # So lange bleiben geloeschte Dokumente im Papierkorb, danach loescht der Worker sie endgueltig
    trash_retention_days: int = 30

    # Gebaute Weboberflaeche (frontend/dist). Im Docker-Image fest "/app/frontend"; fehlt der
    # Ordner (z. B. bei reiner Backend-Entwicklung), laeuft nur die API.
    frontend_dist: str = "../frontend/dist"

    # --- Sicherheit (docs/Sicherheitskonzept.md) -------------------------------------------------
    # Einmal-Code fuer die Ersteinrichtung. Leer = beim Start zufaellig erzeugen, ins Protokoll
    # schreiben und in <DOCUMENTS_PATH>/.einrichtungscode ablegen (core/setup_code.py).
    setup_code: str = ""
    # API-Dokumentation (/docs, /redoc, /openapi.json) - nur zum Entwickeln einschalten
    api_docs: bool = False
    # HTTPS: auto = eigene lokale Zertifizierungsstelle (core/tls.py); off = hinter einem Reverse
    # Proxy, der HTTPS macht (z. B. Synology); custom = eigenes Zertifikat (TLS_CERT_FILE/TLS_KEY_FILE)
    tls_mode: str = "auto"
    tls_dir: str = "./data/tls"  # CA + Server-Zertifikat (Schluessel!) - nicht im Dokumente-Ordner
    tls_hostnames: str = ""  # zusaetzliche Namen/IPs, kommagetrennt, z. B. "nas,nas.local,192.168.1.10"
    tls_cert_file: str = ""
    tls_key_file: str = ""
    https_port: int = 8443  # HTTPS (Weboberflaeche); PORT bleibt fuer HTTP: Umleitung + Zertifikat-Hilfe
    # Anmeldeschutz: ab so vielen Fehlversuchen in Folge sperren (1 Min., dann jeweils doppelt, max. 60)
    login_max_failures: int = 5
    login_max_lock_minutes: int = 60

    jwt_secret: str = JWT_PLACEHOLDER
    # Statt JWT_SECRET von Hand zu setzen: Datei, in der Famulus DMS beim ersten Start selbst einen
    # zufaelligen Schluessel anlegt (API und Worker teilen sich dieselbe Datei, z. B. in einem Volume).
    # Wirkt nur, solange JWT_SECRET leer oder ein Platzhalter ist.
    jwt_secret_file: str = ""
    jwt_access_token_ttl_minutes: int = 15
    jwt_refresh_token_ttl_days: int = 30

    # --- Datenbanksicherungen (core/backup.py) ----------------------------------------------------
    # Ordner fuer die Sicherungsdateien (.dump). Im Container fest "/data/backups".
    backup_path: str = "./backups"
    # So viele Sicherungen bleiben erhalten; aeltere werden nach einer neuen geloescht.
    backup_keep: int = 5
    # Nur zur Anzeige: wo der Sicherungsordner auf dem NAS/PC liegt (im Container sieht man nur /data/backups)
    backup_host_path: str = ""
    # Pfad zu pg_dump(.exe), falls nicht im PATH (Windows) - leer = automatisch suchen
    pg_dump_cmd: str = ""

    tz: str = "Europe/Berlin"

    @model_validator(mode="after")
    def _load_jwt_secret(self) -> "Settings":
        placeholder = self.jwt_secret in ("", JWT_PLACEHOLDER) or "CHANGE_ME" in self.jwt_secret
        if self.jwt_secret_file and placeholder:
            self.jwt_secret = read_or_create_secret(Path(self.jwt_secret_file))
        return self

    @property
    def sqlalchemy_database_url(self) -> str:
        """Fuer den async SQLAlchemy-Engine (homedms/db.py, alembic/env.py) - braucht den
        asyncpg-Treiber im Schema."""
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url

    @property
    def procrastinate_database_url(self) -> str:
        """Fuer Procrastinate/psycopg (homedms/worker.py) - psycopg versteht kein
        "+asyncpg"-Suffix im Schema."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


def read_or_create_secret(path: Path) -> str:
    """Liest den Schluessel aus der Datei oder legt ihn an. Sicher bei gleichzeitigem Start von API
    und Worker: Die Datei wird nur von einem Prozess angelegt (O_EXCL), der andere liest sie."""
    for _ in range(50):
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            value = ""
        if value:
            return value
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:  # ein anderer Prozess schreibt gerade - gleich noch einmal lesen
            time.sleep(0.1)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(secrets.token_hex(32) + "\n")
    raise RuntimeError(f"JWT-Schluesseldatei {path} ist leer oder nicht lesbar")


@lru_cache
def get_settings() -> Settings:
    return Settings()
