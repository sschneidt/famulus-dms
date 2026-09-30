"""Auslieferung der gebauten Weboberflaeche (PWA) durch das Backend - kein eigener Webserver-
Container noetig (docs/Docker-Compose-Entwurf.md Abschnitt 1).

- Dateien aus dem Build (index.html, /assets/*, sw.js, Icons ...) werden direkt ausgeliefert.
- Jede andere Adresse (z. B. /dokumente/123 nach einem Neuladen) bekommt index.html - das
  Routing uebernimmt dann die App im Browser.
- /api, /docs, /redoc, /openapi.json und /health gehoeren dem Backend: unbekannte Pfade dort
  bleiben ein echter 404 statt stillschweigend die App zu liefern.
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

RESERVED_PREFIXES = ("api", "docs", "redoc", "openapi.json", "health")

# Dateinamen in /assets enthalten einen Inhalts-Hash -> duerfen dauerhaft gecacht werden.
# index.html und der Service Worker dagegen immer neu pruefen, sonst sieht man Updates nicht.
IMMUTABLE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"


def mount_frontend(app: FastAPI, dist_dir: str | Path) -> bool:
    """Registriert die Auslieferung, falls ein Build vorhanden ist. Muss NACH allen API-Routen
    aufgerufen werden (die Catch-all-Route wuerde sie sonst verdecken)."""
    root = Path(dist_dir).resolve()
    index = root / "index.html"
    if not index.is_file():
        return False

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        first = path.split("/", 1)[0]
        if first in RESERVED_PREFIXES:
            raise HTTPException(404, "Not Found")
        if path:
            candidate = (root / path).resolve()
            # Schutz vor "../"-Tricks: nur Dateien innerhalb des Build-Ordners
            if candidate.is_file() and candidate.is_relative_to(root):
                cache = IMMUTABLE if first == "assets" else NO_CACHE
                return FileResponse(candidate, headers={"Cache-Control": cache})
            if first == "assets":
                raise HTTPException(404, "Not Found")  # fehlendes Bundle nicht als HTML ausliefern
        return FileResponse(index, headers={"Cache-Control": NO_CACHE})

    return True
