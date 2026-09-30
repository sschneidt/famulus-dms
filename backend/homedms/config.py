"""Zentrale Konfiguration. Env-Variablen spiegeln docker-compose.yml (Repo-Root)."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_role: str = "api"  # "api" oder "worker" - siehe docker-compose.yml

    # Akzeptiert sowohl "postgresql://" als auch "postgresql+asyncpg://" - siehe
    # sqlalchemy_database_url/procrastinate_database_url unten fuer die normalisierten
    # Varianten, die die beiden unterschiedlichen Treiber (asyncpg vs. psycopg) brauchen.
    database_url: str = "postgresql://homedms:changeme@localhost:5432/homedms"

    meilisearch_url: str = "http://localhost:7700"
    meilisearch_key: str = "changeme"

    ollama_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.2:3b"
    ollama_embedding_model: str = "nomic-embed-text"
    # Tesseract-Sprachpakete fuer die Texterkennung (Anforderungsdokument 4.2), "+"-getrennt.
    # Weitere Sprachen: Paket im Dockerfile ergaenzen (tesseract-ocr-<code>) und hier anhaengen.
    ocr_languages: str = "deu+eng"

    ai_caution_level: str = "normal"  # vorsichtig | normal | mutig, siehe Datenmodell 3.7 AIModelConfig

    # Wo Dokument-Dateien liegen. Im Container immer "/data/documents" (fester Mount-Punkt,
    # siehe docker-compose.yml); fuer lokale Entwicklung ohne Docker Default relativ zum cwd.
    documents_path: str = "./data/documents"

    # Gebaute Weboberflaeche (frontend/dist). Im Docker-Image fest "/app/frontend"; fehlt der
    # Ordner (z. B. bei reiner Backend-Entwicklung), laeuft nur die API.
    frontend_dist: str = "../frontend/dist"

    jwt_secret: str = "dev-only-change-me"
    jwt_access_token_ttl_minutes: int = 15
    jwt_refresh_token_ttl_days: int = 30

    tz: str = "Europe/Berlin"

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
