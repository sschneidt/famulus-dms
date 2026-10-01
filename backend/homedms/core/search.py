"""Volltextsuche (Anforderungsdokument 4.4, API-Design: Parameter `q` auf GET /documents).

Zwei Quellen, deren Treffer zusammengefuehrt werden:

1. Meilisearch - tippfehlertolerant ("Wasserschadn" findet "Wasserschaden", "sanitaer" findet
   "Sanitär") und nach Relevanz sortiert.
2. Teilwort-Suche in PostgreSQL - findet Wortteile in zusammengesetzten deutschen Woertern, die
   Meilisearch nicht zerlegt ("schaden" in "Wasserschadens"). Gleichzeitig der Rueckfall, wenn
   Meilisearch nicht erreichbar ist: Die Suche funktioniert dann weiter, nur ohne Tippfehler-Toleranz.

Zugriffsrechte prueft immer die Datenbank (Sichtbarkeitsmodell) - der Suchindex liefert nur
Kandidaten-IDs und Textausschnitte.

Reine Hilfsfunktionen hier (getestet in tests/test_search.py), Meilisearch-Anbindung in
homedms/core/meili.py, Ablauf im Endpunkt homedms/api/routes/documents.py.
"""
import re
import unicodedata
from dataclasses import dataclass

# Markierungen fuer Treffer im Textausschnitt. Steuerzeichen, die in Dokumenttexten nicht
# vorkommen (werden beim Indexieren entfernt) - so kommt nie HTML aus dem Index in die Oberflaeche.
HL_PRE = "\x02"
HL_POST = "\x03"
MAX_INDEXED_TEXT = 100_000
SNIPPET_CHARS = 90  # Zeichen links/rechts vom ersten Treffer beim Teilwort-Ausschnitt
MAX_TERMS = 8


@dataclass(frozen=True)
class Segment:
    text: str
    hit: bool


def clean_text(value: str | None) -> str:
    return (value or "").replace(HL_PRE, " ").replace(HL_POST, " ")


def search_terms(q: str) -> list[str]:
    """Suchwoerter fuer die Teilwort-Suche (ab 2 Zeichen, hoechstens 8, ohne Dubletten)."""
    terms: list[str] = []
    for word in re.findall(r"[\w\-./@€]+", q, flags=re.UNICODE):
        word = word.strip("-./").lower()
        if len(word) >= 2 and word not in terms:
            terms.append(word)
    return terms[:MAX_TERMS]


def like_pattern(term: str) -> str:
    """Fuer ILIKE: % und _ im Suchwort woertlich nehmen."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def segments_from_marked(text: str) -> list[Segment]:
    """Meilisearch-Ausschnitt mit HL_PRE/HL_POST -> Liste von Segmenten fuer die Oberflaeche."""
    result: list[Segment] = []
    for part in re.split(f"({HL_PRE}[^{HL_POST}]*{HL_POST})", text):
        if not part:
            continue
        hit = part.startswith(HL_PRE)
        value = part.strip(HL_PRE + HL_POST)
        if value:
            result.append(Segment(_one_line(value), hit))
    return _merge(result)


def snippet_for_terms(text: str, terms: list[str], radius: int = SNIPPET_CHARS) -> list[Segment]:
    """Ausschnitt um den ersten Treffer, alle Suchwoerter markiert (fuer Teilwort-Treffer)."""
    if not text or not terms:
        return []
    folded = _fold(text)
    positions = [(folded.find(_fold(t)), t) for t in terms]
    positions = [(p, t) for p, t in positions if p >= 0]
    if not positions:
        return []
    first = min(p for p, _ in positions)
    start = max(0, first - radius)
    end = min(len(text), first + radius)
    # an Wortgrenzen ausrichten
    if start > 0:
        space = text.find(" ", start)
        start = space + 1 if 0 <= space < first else start
    if end < len(text):
        space = text.rfind(" ", first, end)
        end = space if space > first else end
    window = text[start:end]
    pattern = re.compile("|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)), re.IGNORECASE)
    segments: list[Segment] = []
    if start > 0:
        segments.append(Segment("… ", False))
    pos = 0
    for m in pattern.finditer(window):
        if m.start() > pos:
            segments.append(Segment(window[pos:m.start()], False))
        segments.append(Segment(m.group(0), True))
        pos = m.end()
    if pos < len(window):
        segments.append(Segment(window[pos:], False))
    if end < len(text):
        segments.append(Segment(" …", False))
    return _merge([Segment(_one_line(s.text), s.hit) for s in segments if s.text])


def _fold(value: str) -> str:
    return unicodedata.normalize("NFC", value).lower()


def _one_line(value: str) -> str:
    return re.sub(r"\s+", " ", value)


def _merge(segments: list[Segment]) -> list[Segment]:
    merged: list[Segment] = []
    for s in segments:
        if merged and merged[-1].hit == s.hit:
            merged[-1] = Segment(merged[-1].text + s.text, s.hit)
        else:
            merged.append(s)
    return merged


def has_hit(segments: list[Segment]) -> bool:
    return any(s.hit for s in segments)


def index_payload(
    document, *, category_name: str | None, property_name: str | None
) -> dict:
    """Ein Dokument so, wie es im Suchindex liegt."""
    return {
        "id": str(document.id),
        "tenant_id": str(document.tenant_id),
        "category_id": str(document.category_id) if document.category_id else None,
        "title": clean_text(document.title),
        "subject": clean_text(document.subject),
        "issuer": clean_text(document.issuer),
        "category": clean_text(category_name),
        "property": clean_text(property_name),
        "ocr_text": clean_text(document.ocr_text)[:MAX_INDEXED_TEXT],
        "created_at": int(document.created_at.timestamp()) if document.created_at else 0,
    }
