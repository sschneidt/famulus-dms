"""Mehrsprachigkeit des Servers (Deutsch, Englisch, Russisch).

Texte stehen im Code auf Deutsch und werden mit _() markiert - der deutsche Text ist zugleich der
Schluessel in den Katalogen en.json/ru.json (wie gettext). Fehlt eine Uebersetzung, erscheint der
deutsche Text. tests/test_i18n.py prueft, dass jeder markierte Text in allen Katalogen steht.

    raise HTTPException(404, _("Dokument nicht gefunden"))
    _("Höchstens {count} Geräte", count=10)        # Platzhalter wie str.format
    _n("{count} Termin", "{count} Termine", n)     # Mehrzahl (Russisch: 3 Formen)

Welche Sprache gilt:
- in API-Anfragen die der Oberflaeche (Kopfzeile Accept-Language, gesetzt von der Weboberflaeche
  bzw. vom Browser) - siehe LanguageMiddleware;
- im Hintergrund (E-Mails, Push) die der Person: with use_language(user.locale): ...
"""
import json
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

LANGUAGES = ("de", "en", "ru")
DEFAULT = "de"

_current: ContextVar[str] = ContextVar("homedms_language", default=DEFAULT)
_DIR = Path(__file__).parent
_CATALOGS: dict[str, dict] = {}


def catalog(lang: str) -> dict:
    if lang not in _CATALOGS:
        path = _DIR / f"{lang}.json"
        _CATALOGS[lang] = json.loads(path.read_text("utf-8")) if path.exists() else {}
    return _CATALOGS[lang]


def current() -> str:
    return _current.get()


def normalize(lang: str | None) -> str:
    code = (lang or "").strip().lower()[:2]
    return code if code in LANGUAGES else DEFAULT


def from_accept_language(header: str | None) -> str:
    """'ru-RU,ru;q=0.9,en;q=0.8' -> 'ru' (erste unterstuetzte Sprache nach Gewichtung)."""
    if not header:
        return DEFAULT
    choices = []
    for i, part in enumerate(header.split(",")):
        tag, _sep, params = part.strip().partition(";")
        q = 1.0
        if params.strip().startswith("q="):
            try:
                q = float(params.strip()[2:])
            except ValueError:
                q = 0.0
        code = tag.strip().lower()[:2]
        if code in LANGUAGES:
            choices.append((-q, i, code))
    return min(choices)[2] if choices else DEFAULT


def set_language(lang: str | None):
    return _current.set(normalize(lang))


@contextmanager
def use_language(lang: str | None):
    token = _current.set(normalize(lang))
    try:
        yield
    finally:
        _current.reset(token)


def gettext(message: str, /, **params) -> str:
    lang = _current.get()
    text = message if lang == DEFAULT else catalog(lang).get(message) or message
    if isinstance(text, list):  # versehentlich Mehrzahl-Eintrag
        text = text[-1]
    return text.format(**params) if params else text


def plural_index(lang: str, n: int) -> int:
    """Index der Mehrzahlform: de/en [eins, viele]; ru [eins, wenige, viele] (CLDR)."""
    n = abs(int(n))
    if lang == "ru":
        if n % 10 == 1 and n % 100 != 11:
            return 0
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return 1
        return 2
    return 0 if n == 1 else 1


def ngettext(singular: str, plural: str, n: int, /, **params) -> str:
    """Katalogeintrag unter dem deutschen Mehrzahl-Text: Liste der Formen."""
    lang = _current.get()
    params.setdefault("count", n)
    if lang == DEFAULT:
        text = singular if n == 1 else plural
    else:
        forms = catalog(lang).get(plural)
        if isinstance(forms, list) and forms:
            text = forms[min(plural_index(lang, n), len(forms) - 1)]
        else:
            text = singular if n == 1 else plural
    return text.format(**params)


def translate_stored(text: str | None) -> str | None:
    """Fuer gespeicherte deutsche Meldungen (z. B. Import-Protokoll): uebersetzen, wenn bekannt."""
    if not text or _current.get() == DEFAULT:
        return text
    value = catalog(_current.get()).get(text)
    return value if isinstance(value, str) and value else text


def format_date(value) -> str:
    """Datum in der Schreibweise der Sprache: 05.10.2026 (de, ru) bzw. 05/10/2026 (en)."""
    return value.strftime("%d/%m/%Y" if _current.get() == "en" else "%d.%m.%Y")


def N_(message: str) -> str:
    """Nur markieren (fuer die Kataloge) - uebersetzt wird spaeter, z. B. beim Anzeigen."""
    return message


_ = gettext
_n = ngettext


class LanguageMiddleware:
    """Setzt die Sprache je Anfrage aus Accept-Language (reines ASGI, auch fuer Fehlerseiten)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        header = None
        for key, value in scope.get("headers", []):
            if key == b"accept-language":
                header = value.decode("latin-1")
                break
        token = _current.set(from_accept_language(header))
        try:
            await self.app(scope, receive, send)
        finally:
            _current.reset(token)
