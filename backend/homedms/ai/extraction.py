"""Metadaten- und Fristenerkennung per Sprachmodell (Anforderungsdokument 4.3 "Klarstellung" und
4.4a "KI-Fristenerkennung im Detail").

Reine Funktionen ohne Datenbank und ohne Modell - getestet in tests/test_extraction.py. Den Ablauf
steuert homedms/tasks/extraction.py.

Leitlinie: Ein kleines lokales Modell irrt sich gelegentlich oder erfindet Angaben. Deshalb wird
jede Antwort streng geprueft und im Zweifel verworfen - lieber eine Frist nicht vorschlagen als
eine falsche. Vorgeschlagene Fristen muessen ohnehin immer vom Nutzer bestaetigt werden.
"""
import re
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

MIN_DEADLINE_CONFIDENCE = 0.5  # Anforderungsdokument 4.4a: darunter wird ein Fund verworfen
MAX_DEADLINES = 5
MIN_QUOTE_OVERLAP = 0.6  # Anteil der Woerter aus "textstelle", die im Dokument vorkommen muessen

RECURRENCE = {  # Antwort des Modells -> (Wiedervorlage.recurrence, Intervall in Monaten)
    "keine": ("none", None),
    "monatlich": ("monthly", 1),
    "vierteljaehrlich": ("custom_months", 3),
    "halbjaehrlich": ("custom_months", 6),
    "jaehrlich": ("yearly", 12),
}

SYSTEM_PROMPT = (
    "Du liest Dokumente eines Privathaushalts und entnimmst ihnen Metadaten und Fristen. "
    "Antworte ausschliesslich mit JSON im vorgegebenen Format. Erfinde nichts: "
    "Was nicht im Text steht, bleibt leer."
)


def build_prompt(text: str, today: date, max_chars: int = 6000) -> tuple[str, str, dict]:
    user = f"""Heutiges Datum: {today.isoformat()}

Aufgaben:
1. dokumentdatum: Datum des Dokuments (Rechnungs- oder Briefdatum) als JJJJ-MM-TT - nur wenn es
   im Text steht, sonst "". Niemals das heutige Datum einsetzen.
2. absender: Firma, Behoerde oder Person, von der das Dokument stammt, sonst "".
3. betrag: Gesamtbetrag in Euro als Zahl mit Punkt (z. B. "42.00"), nur bei Rechnungen oder
   Zahlungsaufforderungen, sonst "".
4. fristen: Termine, zu denen der Empfaenger etwas tun muss oder kann (z. B. Zahlungsfrist,
   Kuendigungsfrist, Widerspruchsfrist, Vertragsende, Pruef- oder Wartungstermin). Je Frist:
   - datum: der LETZTE Tag, an dem der Empfaenger handeln muss, als JJJJ-MM-TT. Relative Angaben
     selbst ausrechnen, ausgehend vom Dokumentdatum bzw. heutigen Datum. Beispiel: "Kuendigung mit
     3 Monaten Frist zum Jahresende" -> die Kuendigung muss 3 Monate VOR dem 31.12. eingehen, also
     ist datum der 30.09. - nicht der 31.12. Ebenso "14 Tage vor Vertragsende" -> 14 Tage davor.
   - bezeichnung: kurz, z. B. "Kuendigungsfrist"
   - konfidenz: Zahl von 0 bis 1
   - textstelle: der Satz aus dem Dokument, aus dem die Frist stammt, woertlich zitiert
   - wiederholung: keine, monatlich, vierteljaehrlich, halbjaehrlich oder jaehrlich
   Gibt es keine Fristen, ist die Liste leer.

Dokumenttext:
\"\"\"
{text[:max_chars]}
\"\"\""""
    schema = {
        "type": "object",
        "properties": {
            "dokumentdatum": {"type": "string"},
            "absender": {"type": "string"},
            "betrag": {"type": "string"},
            "fristen": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "datum": {"type": "string"},
                        "bezeichnung": {"type": "string"},
                        "konfidenz": {"type": "number"},
                        "textstelle": {"type": "string"},
                        "wiederholung": {"type": "string", "enum": list(RECURRENCE)},
                    },
                    "required": ["datum", "bezeichnung", "konfidenz", "textstelle", "wiederholung"],
                },
            },
        },
        "required": ["dokumentdatum", "absender", "betrag", "fristen"],
    }
    return SYSTEM_PROMPT, user, schema


# --- Auswertung -------------------------------------------------------------------------------

def parse_date(value: Any) -> date | None:
    s = str(value or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s) or None
    if m:
        y, mo, d = (int(x) for x in m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})", s)  # falls das Modell deutsch antwortet
        if not m:
            return None
        d, mo, y = (int(x) for x in m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_amount(value: Any) -> Decimal | None:
    s = re.sub(r"[^\d,.\-]", "", str(value or ""))  # "EUR", Leerzeichen, Euro-Zeichen entfernen
    if not s or s in "-.,":
        return None
    if "," in s and "." in s:  # 1.234,56 (deutsch) oder 1,234.56 (englisch)
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        amount = Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None
    return amount if Decimal("0") <= amount < Decimal("100000000") else None


MONATE = {
    1: ("januar", "jan"), 2: ("februar", "feb"), 3: ("maerz", "märz", "mrz", "mär"), 4: ("april", "apr"),
    5: ("mai",), 6: ("juni", "jun"), 7: ("juli", "jul"), 8: ("august", "aug"),
    9: ("september", "sep", "sept"), 10: ("oktober", "okt"), 11: ("november", "nov"), 12: ("dezember", "dez"),
}


def date_in_text(d: date, text: str) -> bool:
    """Steht das Datum in irgendeiner ueblichen Schreibweise im Text? Schutz dagegen, dass das Modell
    ein Datum erfindet (z. B. das heutige, das es als Rechenhilfe mitbekommt)."""
    t = re.sub(r"\s+", " ", text.lower())
    day, mon, yr = d.day, d.month, d.year
    numeric = {
        f"{day:02d}.{mon:02d}.{yr}", f"{day}.{mon}.{yr}", f"{day:02d}.{mon:02d}.{yr % 100:02d}",
        f"{day}.{mon}.{yr % 100:02d}", d.isoformat(), f"{day:02d}/{mon:02d}/{yr}", f"{day}/{mon}/{yr}",
    }
    for candidate in numeric:
        if re.search(rf"(?<![\d.]){re.escape(candidate)}(?![\d])", t):
            return True
    for name in MONATE[mon]:
        if re.search(rf"(?<!\d)0?{day}\.? ?{re.escape(name)}\.? ?{yr}(?!\d)", t):
            return True
    return False


def _confidence(value: Any) -> float:
    try:
        c = float(value)
    except (TypeError, ValueError):
        return 0.0
    if c > 1:
        c /= 100
    return min(max(c, 0.0), 1.0)


def _words(s: str) -> list[str]:
    return re.findall(r"\w+", s.lower())


def quote_supported(quote: str, document_text: str) -> bool:
    """Schutz gegen erfundene Fristen: Die zitierte Textstelle muss (weitgehend) im Dokument stehen.
    Leichte Abweichungen (OCR-Fehler, Satzzeichen, Umformulierung einzelner Woerter) sind erlaubt."""
    words = _words(quote)
    if len(words) < 2:
        return False
    doc_words = set(_words(document_text))
    return sum(w in doc_words for w in words) / len(words) >= MIN_QUOTE_OVERLAP


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    year, month = d.year + y, m + 1
    return date(year, month, min(d.day, monthrange(year, month)[1]))


@dataclass(frozen=True)
class DeadlineProposal:
    due_date: date
    label: str
    confidence: float
    snippet: str
    recurrence: str
    interval_months: int | None


@dataclass
class ExtractionResult:
    document_date: date | None = None
    issuer: str | None = None
    amount: Decimal | None = None
    deadlines: list[DeadlineProposal] = field(default_factory=list)
    discarded: list[str] = field(default_factory=list)  # Begruendungen fuer Log/Nachvollziehbarkeit


def parse_extraction(answer: dict[str, Any], document_text: str, today: date) -> ExtractionResult:
    result = ExtractionResult()

    doc_date = parse_date(answer.get("dokumentdatum"))
    if doc_date and date(1950, 1, 1) <= doc_date <= today + timedelta(days=365):
        if date_in_text(doc_date, document_text):
            result.document_date = doc_date
        else:
            result.discarded.append(f"Dokumentdatum {doc_date.isoformat()} steht nicht im Text")
    issuer = str(answer.get("absender") or "").strip()
    result.issuer = issuer[:300] or None
    result.amount = parse_amount(answer.get("betrag"))

    seen: set[tuple[date, str]] = set()
    fristen = answer.get("fristen") or []
    for raw in fristen if isinstance(fristen, list) else []:
        if not isinstance(raw, dict):
            continue
        label = (str(raw.get("bezeichnung") or "").strip() or "Frist")[:200]
        due = parse_date(raw.get("datum"))
        confidence = _confidence(raw.get("konfidenz"))
        snippet = str(raw.get("textstelle") or "").strip()[:1000]
        recurrence, interval = RECURRENCE.get(str(raw.get("wiederholung") or "keine"), ("none", None))

        if due is None:
            result.discarded.append(f"{label}: kein gueltiges Datum ({raw.get('datum')!r})")
            continue
        if confidence < MIN_DEADLINE_CONFIDENCE:
            result.discarded.append(f"{label}: Konfidenz {confidence:.0%} unter {MIN_DEADLINE_CONFIDENCE:.0%}")
            continue
        if not quote_supported(snippet, document_text):
            result.discarded.append(f"{label}: Textstelle steht nicht im Dokument")
            continue
        if due < today:
            if interval is None:
                result.discarded.append(f"{label}: {due.isoformat()} liegt in der Vergangenheit")
                continue
            while due < today:  # wiederkehrende Frist: naechsten kuenftigen Termin nehmen
                due = add_months(due, interval)
        if due > today + timedelta(days=365 * 30):
            result.discarded.append(f"{label}: {due.isoformat()} unplausibel weit in der Zukunft")
            continue
        if (due, label.lower()) in seen:
            continue
        seen.add((due, label.lower()))
        result.deadlines.append(DeadlineProposal(due, label, confidence, snippet, recurrence, interval))

    if len(result.deadlines) > MAX_DEADLINES:
        result.deadlines.sort(key=lambda d: d.confidence, reverse=True)
        result.discarded.append(f"{len(result.deadlines) - MAX_DEADLINES} weitere Fristen (Obergrenze {MAX_DEADLINES})")
        result.deadlines = sorted(result.deadlines[:MAX_DEADLINES], key=lambda d: d.due_date)
    return result
