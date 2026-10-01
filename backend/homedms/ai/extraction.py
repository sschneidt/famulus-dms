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

from homedms.core.dates import add_months  # noqa: F401  (auch fuer bestehende Importe)
from homedms.core.addresses import Address, parse_address
from homedms.core.naming import clean_subject
from homedms.core.payments import is_payment

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
3. betreff: worum es im Dokument geht, in 2 bis 6 Woertern nach dem Muster
   "<Art des Dokuments> <Anlass oder Gegenstand>" - nur mit Woertern aus dem Text, ohne Absender,
   ohne Datum, ohne Betrag.
4. betrag: Gesamtbetrag in Euro als Zahl mit Punkt (z. B. "42.00"), nur bei Rechnungen oder
   Zahlungsaufforderungen, sonst "".
5. objektadresse: Adresse des Hauses oder der Wohnung, um die es im Dokument geht (z. B. bei
   "Objekt", "Leistungsort", "Baustelle", "Verbrauchsstelle", "Versicherungsort"). Steht keine
   eigene Objektadresse im Text, die Anschrift des Empfaengers. NIEMALS die Adresse des Absenders
   aus Briefkopf oder Fusszeile. Felder: strasse (mit Hausnummer), plz, ort - sonst leer.
6. fristen: Termine, zu denen der Empfaenger etwas tun muss oder kann (z. B. Zahlungsfrist,
   Kuendigungsfrist, Widerspruchsfrist, Vertragsende, Pruef- oder Wartungstermin). Je Frist:
   - datum: der LETZTE Tag, an dem der Empfaenger handeln muss, als JJJJ-MM-TT. Steht im Text ein
     Datum, genau dieses nehmen. Relative Angaben selbst ausrechnen (bei einer Kuendigungsfrist
     "zum" einem Termin liegt der letzte Tag entsprechend VOR diesem Termin).
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
            "betreff": {"type": "string"},
            "betrag": {"type": "string"},
            "objektadresse": {
                "type": "object",
                "properties": {"strasse": {"type": "string"}, "plz": {"type": "string"}, "ort": {"type": "string"}},
                "required": ["strasse", "plz", "ort"],
            },
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
        "required": ["dokumentdatum", "absender", "betreff", "betrag", "objektadresse", "fristen"],
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


def subject_supported(subject: str, document_text: str) -> bool:
    """Schutz gegen erfundene oder aus dem Prompt abgeschriebene Betreffs: Mindestens die Haelfte
    der Woerter (ab 4 Buchstaben) muss im Text vorkommen - als Wortstamm, damit z. B.
    "Wasserschaden" auch zu "Wasserschadens" passt."""
    words = [w for w in _words(subject) if len(w) >= 4 and not w.isdigit()]
    if not words:
        return False
    text = document_text.lower()
    hits = sum(w[: max(4, len(w) - 2)] in text for w in words)
    return hits * 2 >= len(words)


def quote_supported(quote: str, document_text: str) -> bool:
    """Schutz gegen erfundene Fristen: Die zitierte Textstelle muss (weitgehend) im Dokument stehen.
    Leichte Abweichungen (OCR-Fehler, Satzzeichen, Umformulierung einzelner Woerter) sind erlaubt."""
    words = _words(quote)
    if len(words) < 2:
        return False
    doc_words = set(_words(document_text))
    return sum(w in doc_words for w in words) / len(words) >= MIN_QUOTE_OVERLAP



# --- Datum aus der Textstelle statt Rechenergebnis des Modells -------------------------------
# Erfahrung mit llama3.2:3b: Das Modell uebernimmt gern Beispiel- oder Tagesdaten aus dem Prompt,
# statt das Datum aus dem Text zu nehmen, und rechnet relative Fristen falsch. Beides laesst sich aus
# der zitierten Textstelle zuverlaessig ohne Modell bestimmen.

_MONTH_NAMES = {name: num for num, names in MONATE.items() for name in names}
_DATE_PATTERNS = [
    re.compile(r"(?<![\d.])(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4}|\d{2})(?!\d)"),  # 15.10.2026 / 15.10.26
    re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)"),  # 2026-10-15
    re.compile(r"(?<!\d)(\d{1,2})\.?\s?(" + "|".join(sorted(map(re.escape, _MONTH_NAMES), key=len, reverse=True))
               + r")\.?\s?(\d{4})(?!\d)"),  # 15. Oktober 2026
]


def dates_in(text: str) -> list[tuple[int, date]]:
    """Alle ausgeschriebenen Daten im Text mit ihrer Position (fuer die Wahl "Datum nach 'bis'")."""
    t = text.lower()
    found: dict[int, date] = {}
    for i, pattern in enumerate(_DATE_PATTERNS):
        for m in pattern.finditer(t):
            a, b, c = m.groups()
            if i == 0:
                day, month, year = int(a), int(b), int(c)
                year += 2000 if year < 100 else 0
            elif i == 1:
                year, month, day = int(a), int(b), int(c)
            else:
                day, month, year = int(a), _MONTH_NAMES[b], int(c)
            try:
                found.setdefault(m.start(), date(year, month, day))
            except ValueError:
                continue
    return sorted(found.items())


def explicit_deadline(snippet: str) -> date | None:
    """Das Datum, das die Textstelle ausdruecklich nennt - bei mehreren das nach "bis"/"zum"/..."""
    found = dates_in(snippet)
    if len(found) == 1:
        return found[0][1]
    for pos, d in found:
        if re.search(r"(bis|bis zum|bis spaetestens|bis spätestens|spaetestens|spätestens|zum|am|faellig am|fällig am)\s*$",
                     snippet[:pos].lower().strip()):
            return d
    return None


_NUMBER_WORDS = {"ein": 1, "einen": 1, "einem": 1, "einer": 1, "zwei": 2, "drei": 3, "vier": 4, "fuenf": 5,
                 "fünf": 5, "sechs": 6, "acht": 8, "neun": 9, "zehn": 10, "zwoelf": 12, "zwölf": 12}
_RELATIVE = re.compile(
    r"(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")\s+(monat|monaten|monate|woche|wochen)\b[^.;]{0,40}?"
    r"\b(?:zum|zu[mr]?|vor dem|vor)\s+(?:ende\s+(?:des|eines)\s+)?"
    r"(jahresende|kalenderjahres|kalenderjahr|jahres|quartalsende|quartals|kalenderquartals|monatsende|monats)\b"
)
_PERIOD = {"jahresende": 12, "kalenderjahres": 12, "kalenderjahr": 12, "jahres": 12,
           "quartalsende": 3, "quartals": 3, "kalenderquartals": 3, "monatsende": 1, "monats": 1}


def relative_deadline(snippet: str, today: date) -> tuple[date, int] | None:
    """Standardfristen wie "3 Monate zum Jahresende" oder "6 Wochen zum Quartalsende" selbst
    ausrechnen: letzter Tag, an dem man noch handeln kann, fuer das naechste noch erreichbare
    Periodenende. Liefert (Datum, Periodenlaenge in Monaten) - die Frist wiederholt sich jede Periode."""
    m = _RELATIVE.search(snippet.lower())
    if not m:
        return None
    amount_raw, unit, period_raw = m.groups()
    amount = int(amount_raw) if amount_raw.isdigit() else _NUMBER_WORDS[amount_raw]
    period = _PERIOD[period_raw]
    # Periodenenden ab dem aktuellen Monat durchgehen, bis die Frist noch nicht verstrichen ist
    for offset in range(0, 12 * 3 + 1):
        probe = add_months(date(today.year, today.month, 1), offset)
        if probe.month % period != 0:
            continue
        period_end = date(probe.year, probe.month, monthrange(probe.year, probe.month)[1])
        if unit.startswith("monat"):
            deadline = add_months(period_end, -amount)
            deadline = date(deadline.year, deadline.month, monthrange(deadline.year, deadline.month)[1])
        else:
            deadline = period_end - timedelta(weeks=amount)
        if deadline >= today:
            return deadline, period
    return None


_CANONICAL_LABELS = [  # (Stichworte, einheitliche Bezeichnung) - erste passende gewinnt
    (("kuendig", "kündig"), "Kündigungsfrist"),
    (("widerspruch", "einspruch"), "Widerspruchsfrist"),
    (("zahlbar", "zahlung", "faellig", "fällig", "ueberweis", "überweis"), "Zahlungsfrist"),
    (("vertragsende", "laufzeitende", "ablauf des vertrag"), "Vertragsende"),
    (("tuev", "tüv", "hauptuntersuchung"), "TÜV-Termin"),
    (("wartung", "pruefung", "prüfung"), "Prüftermin"),
]


def normalize_label(label: str, snippet: str) -> str:
    """Einheitliche Bezeichnungen statt Textschnipseln: Das Modell liefert mal "Zahlungsfrist", mal
    "zahlbar bis". Zuerst zaehlt die Bezeichnung selbst; nur wenn sie wie ein Satzfragment aussieht
    (klein geschrieben), wird zusaetzlich die Textstelle herangezogen."""
    for source in (label, snippet if label[:1].islower() else ""):
        lowered = source.lower()
        for keywords, canonical in _CANONICAL_LABELS:
            if any(k in lowered for k in keywords):
                return canonical
    return label[:1].upper() + label[1:]


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
    subject: str | None = None
    address: Address | None = None
    amount: Decimal | None = None
    deadlines: list[DeadlineProposal] = field(default_factory=list)
    past_payments: list[DeadlineProposal] = field(default_factory=list)  # bereits verstrichene Zahlungsfristen
    discarded: list[str] = field(default_factory=list)  # Begruendungen fuer Log/Nachvollziehbarkeit
    corrected: list[str] = field(default_factory=list)  # Daten, die aus der Textstelle korrigiert wurden


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
    subject = clean_subject(answer.get("betreff"))
    if subject and subject_supported(subject, document_text):
        result.subject = subject
    elif subject:
        result.discarded.append(f"Betreff {subject!r} passt nicht zum Text")
    result.address = parse_address(answer.get("objektadresse"), document_text, result.issuer)
    if result.address is None and isinstance(answer.get("objektadresse"), dict) and any(answer["objektadresse"].values()):
        result.discarded.append(f"Objektadresse {answer['objektadresse']!r} nicht belegt oder Absenderadresse")
    result.amount = parse_amount(answer.get("betrag"))

    seen: set[tuple[date, str]] = set()
    fristen = answer.get("fristen") or []
    for raw in fristen if isinstance(fristen, list) else []:
        if not isinstance(raw, dict):
            continue
        snippet_raw = str(raw.get("textstelle") or "").strip()
        label = normalize_label((str(raw.get("bezeichnung") or "").strip() or "Frist")[:200], snippet_raw)
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
        explicit = explicit_deadline(snippet)
        relative = None if explicit else relative_deadline(snippet, today)
        if explicit and explicit != due:
            result.corrected.append(f"{label}: {due.isoformat()} -> {explicit.isoformat()} (Datum aus der Textstelle)")
            due = explicit
        elif relative:
            rel_due, period = relative
            if rel_due != due:
                result.corrected.append(f"{label}: {due.isoformat()} -> {rel_due.isoformat()} (Frist aus der Textstelle berechnet)")
            due = rel_due
            if recurrence == "none":  # "zum Jahresende" & Co. gilt jede Periode wieder
                recurrence, interval = {12: ("yearly", 12), 3: ("custom_months", 3), 1: ("monthly", 1)}[period]
        if due < today:
            if interval is None and is_payment(label):
                # Verstrichene Zahlungsfrist: wichtig fuer den Zahlungsstatus (core/payments.py) -
                # lange her = wohl bezahlt, kuerzlich = nachfragen
                if (due, label.lower()) not in seen:
                    seen.add((due, label.lower()))
                    result.past_payments.append(DeadlineProposal(due, label, confidence, snippet, "none", None))
                continue
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
