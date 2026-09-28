"""Schlanker Client fuer die lokale Ollama-Instanz (Anforderungsdokument 4.3, KI-Betriebsmodell
"lokal bevorzugt"). Nur die zwei Aufrufe, die die Klassifikation braucht:

- embed(): Text -> Vektor (Stufe 1, Vergleich mit den Kategorie-Exemplaren per pgvector)
- chat_json(): Frage an das Chat-Modell mit erzwungener JSON-Antwort (Stufe 2)

Bewusst als eigene kleine Klasse statt direkt im Task, damit sich (a) spaeter ein externer
Anbieter dahinter tauschen laesst und (b) Tests eine Attrappe einsetzen koennen, ohne dass ein
echtes Sprachmodell laufen muss (siehe tests/integration).
"""
import json
from typing import Any

import httpx

from homedms.config import get_settings

# Texte werden vor dem Senden gekuerzt: Das Embedding-Modell verarbeitet ohnehin nur einen
# begrenzten Kontext, und fuer die Kategorie reicht der Anfang eines Dokuments praktisch immer.
MAX_TEXT_CHARS = 3000


class OllamaError(RuntimeError):
    """Ollama nicht erreichbar, Modell fehlt oder Antwort unbrauchbar."""


class OllamaClient:
    def __init__(
        self,
        base_url: str | None = None,
        chat_model: str | None = None,
        embedding_model: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_url).rstrip("/")
        self.chat_model = chat_model or settings.ollama_chat_model
        self.embedding_model = embedding_model or settings.ollama_embedding_model
        self._transport = transport

    def _client(self, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=timeout, transport=self._transport)

    async def _post(self, path: str, payload: dict, timeout: float) -> dict:
        try:
            async with self._client(timeout) as client:
                resp = await client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama nicht erreichbar ({self.base_url}): {exc}") from exc
        if resp.status_code != 200:
            hint = " - ist das Modell schon heruntergeladen? (docker compose logs ollama-init)" if resp.status_code == 404 else ""
            raise OllamaError(f"Ollama {path} antwortete {resp.status_code}: {resp.text[:300]}{hint}")
        return resp.json()

    async def embed(self, text: str) -> list[float]:
        # nomic-embed-text erwartet ein Aufgaben-Praefix; dasselbe fuer Exemplare und neue
        # Dokumente, damit die Vektoren vergleichbar sind.
        payload = {"model": self.embedding_model, "input": "classification: " + text[:MAX_TEXT_CHARS]}
        data = await self._post("/api/embed", payload, timeout=120)
        try:
            return [float(x) for x in data["embeddings"][0]]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise OllamaError(f"Unerwartete Embedding-Antwort: {str(data)[:200]}") from exc

    async def chat_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.chat_model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "stream": False,
            "format": schema,  # Ollama erzwingt damit eine Antwort passend zum JSON-Schema
            "options": {"temperature": 0, "num_ctx": 4096},
        }
        # Das erste Laden des Modells in den Arbeitsspeicher kann auf einem NAS dauern.
        data = await self._post("/api/chat", payload, timeout=300)
        content = (data.get("message") or {}).get("content", "")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"Chat-Antwort ist kein gueltiges JSON: {content[:200]}") from exc
