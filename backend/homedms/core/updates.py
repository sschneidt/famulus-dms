"""Auf neue Versionen pruefen (Seite "Diagnose", Knopf "Auf Updates pruefen").

Gefragt wird nur auf Knopfdruck eines Admins, nie von selbst: ein GET auf die Release-Liste auf GitHub
(UPDATE_CHECK_URL, Standard: neuestes Release von sschneidt/famulus-dms). Es werden keine Daten uebertragen
ausser dem, was jede Web-Anfrage verraet (Adresse des Servers); der Client nennt sich "famulus-dms/<Version>".
Leere UPDATE_CHECK_URL schaltet die Pruefung aus. Das Ergebnis wird kurz gemerkt (GitHub erlaubt ohne
Anmeldung nur 60 Anfragen je Stunde und Adresse).
"""
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from homedms import __version__
from homedms.config import get_settings
from homedms.i18n import _

logger = logging.getLogger("homedms.updates")

CACHE_SECONDS = 600
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)")
_cache: tuple[float, "UpdateInfo"] | None = None


class UpdateCheckError(Exception):
    """Mit einer Meldung, die der Anwender lesen darf."""


@dataclass(frozen=True)
class UpdateInfo:
    current: str
    latest: str
    available: bool
    url: str  # Seite des Releases mit den Aenderungen
    published_at: datetime | None
    checked_at: datetime


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = _VERSION.match(text.strip())
    return (int(match[1]), int(match[2]), int(match[3])) if match else None


def is_newer(latest: str, current: str) -> bool:
    new, old = parse_version(latest), parse_version(current)
    return bool(new and old and new > old)


def enabled() -> bool:
    return bool(get_settings().update_check_url.strip())


def clear_cache() -> None:
    global _cache
    _cache = None


async def check(client: httpx.AsyncClient | None = None, *, force: bool = False) -> UpdateInfo:
    global _cache
    url = get_settings().update_check_url.strip()
    if not url:
        raise UpdateCheckError(_("Die Prüfung auf Updates ist abgeschaltet (UPDATE_CHECK_URL ist leer)."))
    if not force and _cache and time.monotonic() - _cache[0] < CACHE_SECONDS and _cache[1].current == __version__:
        return _cache[1]

    own = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(10), follow_redirects=True)
    try:
        response = await client.get(url, headers={"Accept": "application/vnd.github+json", "User-Agent": f"famulus-dms/{__version__}"})
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning("Update-Prüfung: %s", exc)
        raise UpdateCheckError(_("Die Update-Seite antwortet mit Fehler {code}.", code=exc.response.status_code)) from exc
    except httpx.HTTPError as exc:
        logger.warning("Update-Prüfung: %s", exc)
        raise UpdateCheckError(_("Die Update-Seite ist nicht erreichbar. Hat der Server Zugang zum Internet?")) from exc
    finally:
        if own:
            await client.aclose()
    try:
        release = response.json()
    except ValueError as exc:
        logger.warning("Update-Prüfung: keine gültige Antwort (%s)", exc)
        raise UpdateCheckError(_("Die Antwort der Update-Seite ist nicht lesbar.")) from exc

    tag = str(release.get("tag_name", "")) if isinstance(release, dict) else ""
    if parse_version(tag) is None:
        raise UpdateCheckError(_("Die Antwort der Update-Seite ist nicht lesbar."))
    latest = tag.strip().lstrip("v")
    published = release.get("published_at")
    try:
        published_at = datetime.fromisoformat(published.replace("Z", "+00:00")) if published else None
    except (AttributeError, ValueError):
        published_at = None
    info = UpdateInfo(
        current=__version__, latest=latest, available=is_newer(latest, __version__),
        url=str(release.get("html_url") or ""), published_at=published_at, checked_at=datetime.now(timezone.utc),
    )
    _cache = (time.monotonic(), info)
    return info
