"""Schlanke Meilisearch-Anbindung ueber HTTP (bewusst ohne zusaetzliche Bibliothek).

Ein gemeinsamer Index "documents" fuer alle Haushalte; jede Suche filtert auf tenant_id, und die
Zugriffsrechte prueft danach ohnehin die Datenbank (homedms/core/search.py).
"""
import logging
from typing import Any

import httpx

from homedms.config import get_settings
from homedms.core.search import HL_POST, HL_PRE

logger = logging.getLogger("homedms.core.meili")

INDEX = "documents"
SETTINGS = {
    # Reihenfolge = Gewichtung: ein Treffer im Titel zaehlt mehr als einer irgendwo im Text
    "searchableAttributes": ["title", "subject", "issuer", "property", "category", "ocr_text"],
    "filterableAttributes": ["tenant_id", "category_id"],
    "sortableAttributes": ["created_at"],
}
MAX_HITS = 1000


class SearchUnavailable(Exception):
    pass


class MeiliClient:
    def __init__(self, base_url: str, api_key: str, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._transport = transport
        self._settings_applied = False

    async def _request(self, method: str, path: str, json: Any = None, timeout: float = 10) -> dict:
        if not self.base_url:
            raise SearchUnavailable("Meilisearch ist nicht eingerichtet (MEILISEARCH_URL leer)")
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=timeout, transport=self._transport,
                headers={"Authorization": f"Bearer {self.api_key}"},
            ) as client:
                resp = await client.request(method, path, json=json)
        except httpx.HTTPError as exc:
            raise SearchUnavailable(f"Meilisearch nicht erreichbar ({self.base_url}): {exc}") from exc
        if resp.status_code >= 400:
            raise SearchUnavailable(f"Meilisearch {method} {path}: {resp.status_code} {resp.text[:300]}")
        return resp.json() if resp.content else {}

    async def ensure_settings(self) -> None:
        """Index anlegen/einstellen (idempotent; Meilisearch arbeitet Auftraege je Index der Reihe
        nach ab, deshalb muss nicht auf die Fertigstellung gewartet werden)."""
        if self._settings_applied:
            return
        if not await self._index_exists():
            await self._request("POST", "/indexes", {"uid": INDEX, "primaryKey": "id"})
        await self._request("PATCH", f"/indexes/{INDEX}/settings", SETTINGS)
        self._settings_applied = True

    async def _index_exists(self) -> bool:
        try:
            await self._request("GET", f"/indexes/{INDEX}")
            return True
        except SearchUnavailable as exc:
            if "404" in str(exc):
                return False
            raise

    async def upsert(self, payload: dict) -> None:
        await self.ensure_settings()
        await self._request("POST", f"/indexes/{INDEX}/documents?primaryKey=id", [payload])

    async def delete(self, document_id: str) -> None:
        await self._request("DELETE", f"/indexes/{INDEX}/documents/{document_id}")

    async def search(self, q: str, tenant_id: str, category_id: str | None = None) -> list[dict]:
        """Treffer nach Relevanz: [{"id": ..., "_formatted": {...}}]."""
        await self.ensure_settings()
        filters = [f'tenant_id = "{tenant_id}"']
        if category_id:
            filters.append(f'category_id = "{category_id}"')
        data = await self._request("POST", f"/indexes/{INDEX}/search", {
            "q": q,
            "filter": " AND ".join(filters),
            "limit": MAX_HITS,
            "attributesToRetrieve": ["id"],
            "attributesToCrop": ["ocr_text"],
            "cropLength": 24,
            "cropMarker": "…",
            "attributesToHighlight": ["title", "subject", "issuer", "property", "ocr_text"],
            "highlightPreTag": HL_PRE,
            "highlightPostTag": HL_POST,
        })
        return data.get("hits", [])


_client: MeiliClient | None = None


def client() -> MeiliClient:
    """Gemeinsamer Client je Prozess - Testpunkt (tests ersetzen ihn per monkeypatch)."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = MeiliClient(settings.meilisearch_url, settings.meilisearch_key)
    return _client


async def index_document(db, document_id) -> None:
    """Suchindex fuer ein Dokument aktualisieren (oder entfernen, wenn geloescht/im Papierkorb).
    Fehler werden nur protokolliert: Die Suche faellt dann auf die Datenbank zurueck, und beim
    naechsten Start des API-Containers wird ohnehin alles neu eingereiht."""
    from homedms.core.search import index_payload
    from homedms.models.document import Category, Document, Property

    document = await db.get(Document, document_id)
    try:
        if document is None or document.deleted_at is not None:
            await client().delete(str(document_id))
            return
        category = await db.get(Category, document.category_id) if document.category_id else None
        prop = await db.get(Property, document.property_id) if document.property_id else None
        await client().upsert(index_payload(
            document, category_name=category.name if category else None, property_name=prop.name if prop else None,
        ))
    except SearchUnavailable as exc:
        logger.warning("Suchindex fuer %s nicht aktualisiert: %s", document_id, exc)
