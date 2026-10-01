"""Objekt-Adressen (Haus/Wohnung) fuer die Ablage pro Objekt.

Nutzerwunsch: Unter "Haus & Reparaturen" (sowie "Wohnen & Nebenkosten" und bei
Gebaeude-Versicherungen) bekommt jede Adresse einen eigenen Unterordner "<Ort> <Strasse Nr>", in dem
alle Unterlagen zu diesem Objekt landen.

Die Adresse liest die KI aus dem Dokument (Objekt-/Leistungsadresse, sonst Empfaengeranschrift).
Kleine Modelle greifen gern daneben - vor allem zur Absenderadresse im Briefkopf oder in der
Fusszeile. Deshalb wird jede Antwort hier gegen den Text geprueft (reine Funktionen, getestet in
tests/test_addresses.py).
"""
import re
import unicodedata
from dataclasses import dataclass

# Kategorie.property_mode
PROPERTY_MODES = ("none", "all", "buildings")
NO_ADDRESS_FOLDER = "_Ohne Adresse"

_BUILDING_INSURANCE = re.compile(
    r"wohngeb(?:ä|ae|a)ude|geb(?:ä|ae|a)udeversicherung|hausrat|elementarschaden|feuerversicherung|glasversicherung",
    re.IGNORECASE,
)
# Zeilen mit solchen Angaben gehoeren zum Briefkopf/zur Fusszeile des Absenders
_SENDER_LINE = re.compile(
    r"\b(tel|telefon|fax|e-?mail|www|http|ust|steuer-?nr|iban|bic|hrb|amtsgericht|geschäftsführ|geschaeftsfuehr)\b|@",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Address:
    street: str  # inkl. Hausnummer, z. B. "Musterstraße 5"
    postal_code: str
    city: str

    @property
    def match_key(self) -> str:
        return f"{self.postal_code}|{normalize_street(self.street)}"

    @property
    def default_name(self) -> str:
        return f"{self.city} {self.street}"


def _ascii_lower(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()
    for src, dst in (("ß", "ss"), ("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        value = value.replace(src, dst)
    return value


def normalize_street(street: str) -> str:
    """"Musterstraße 5", "Musterstr. 5", "Muster-Strasse 5" -> "musterstr5"."""
    s = _ascii_lower(street)
    s = re.sub(r"strasse\b|str\b\.?", "str", s)
    return re.sub(r"[^a-z0-9]", "", s)


def _squash(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip(" ,.;")


def _street_name(street: str) -> str:
    """Strassenname ohne Hausnummer, normalisiert (fuer die Suche im Text)."""
    name = re.split(r"\s+\d", street, maxsplit=1)[0]
    return normalize_street(name)


def address_supported(address: Address, document_text: str, issuer: str | None = None) -> bool:
    """Steht die Adresse wirklich im Text - und nicht nur im Briefkopf/der Fusszeile des Absenders?"""
    street_key = _street_name(address.street)
    if len(street_key) < 4:
        return False
    lines = document_text.splitlines()
    issuer_key = normalize_street(issuer) if issuer else ""
    found_outside_sender = False
    for i, line in enumerate(lines):
        if street_key not in normalize_street(line):
            continue
        context = " ".join(lines[max(0, i - 2): i + 3])
        if address.postal_code not in context:
            continue
        near_issuer = issuer_key and any(
            issuer_key[:12] in normalize_street(lines[j]) for j in range(max(0, i - 2), i + 1)
        )
        if _SENDER_LINE.search(line) or near_issuer:
            continue  # Absenderadresse
        found_outside_sender = True
    return found_outside_sender


def parse_address(raw: object, document_text: str, issuer: str | None = None) -> Address | None:
    """KI-Antwort {"strasse", "plz", "ort"} pruefen. Nur deutsche Postleitzahlen (5 Ziffern)."""
    if not isinstance(raw, dict):
        return None
    street = _squash(raw.get("strasse"))
    postal_code = _squash(raw.get("plz"))
    city = _squash(raw.get("ort"))
    if not re.fullmatch(r"\d{5}", postal_code) or not city or not re.search(r"[A-Za-zÄÖÜäöüß]{3}.*\d", street):
        return None
    address = Address(street=street[:200], postal_code=postal_code, city=city[:100])
    return address if address_supported(address, document_text, issuer) else None


def uses_property_folder(mode: str, document_text: str) -> bool:
    """Bekommt ein Dokument dieser Kategorie einen Objekt-Unterordner?"""
    if mode == "all":
        return True
    if mode == "buildings":
        return bool(_BUILDING_INSURANCE.search(document_text or ""))
    return False
