"""Objekt-Adressen (homedms/core/addresses.py)."""
import pytest

from homedms.core.addresses import Address, normalize_street, parse_address, uses_property_folder

RECHNUNG = """Sanitär Müller GmbH
Industriestraße 3, 70565 Stuttgart
Tel. 0711 123456

Familie Muster
Musterstraße 5
70173 Stuttgart

Rechnung Nr. 4711
Objekt: Ferienwohnung, Seeweg 12a, 88709 Meersburg
Reparatur Wasserschaden im Bad

USt-IdNr. DE123 · IBAN DE00 1234 · Industriestraße 3 · 70565 Stuttgart"""


@pytest.mark.parametrize(
    ("a", "b"),
    [("Musterstraße 5", "Musterstr. 5"), ("Muster-Strasse 5", "musterstr 5"), ("Seeweg 12a", "Seeweg 12 a")],
)
def test_normalize_street_gleich(a, b):
    assert normalize_street(a) == normalize_street(b)


def test_normalize_street_unterschiedlich():
    assert normalize_street("Musterstraße 5") != normalize_street("Musterstraße 7")


def test_objektadresse_wird_akzeptiert():
    a = parse_address({"strasse": "Seeweg 12a", "plz": "88709", "ort": "Meersburg"}, RECHNUNG, "Sanitär Müller GmbH")
    assert a == Address("Seeweg 12a", "88709", "Meersburg")
    assert a.default_name == "Meersburg Seeweg 12a"


def test_empfaengeradresse_wird_akzeptiert():
    a = parse_address({"strasse": "Musterstr. 5", "plz": "70173", "ort": "Stuttgart"}, RECHNUNG, "Sanitär Müller GmbH")
    assert a is not None and a.match_key == Address("Musterstraße 5", "70173", "Stuttgart").match_key


def test_absenderadresse_wird_verworfen():
    # steht nur im Briefkopf (direkt unter dem Absender) und in der Fusszeile (USt/IBAN)
    assert parse_address({"strasse": "Industriestraße 3", "plz": "70565", "ort": "Stuttgart"}, RECHNUNG, "Sanitär Müller GmbH") is None


@pytest.mark.parametrize(
    "raw",
    [
        {"strasse": "Erfundenweg 1", "plz": "12345", "ort": "Nirgendwo"},  # steht nicht im Text
        {"strasse": "Seeweg 12a", "plz": "8870", "ort": "Meersburg"},  # PLZ ungueltig
        {"strasse": "Seeweg", "plz": "88709", "ort": "Meersburg"},  # ohne Hausnummer
        {"strasse": "Seeweg 12a", "plz": "70173", "ort": "Meersburg"},  # PLZ passt nicht zur Strasse
        {"strasse": "", "plz": "", "ort": ""},
        "Seeweg 12a",
        None,
    ],
)
def test_ungueltige_adressen(raw):
    assert parse_address(raw, RECHNUNG, "Sanitär Müller GmbH") is None


def test_objektordner_je_kategorie():
    assert uses_property_folder("all", "egal")
    assert not uses_property_folder("none", "Wohngebäudeversicherung")
    assert uses_property_folder("buildings", "Ihre Wohngebäudeversicherung, Beitrag 2027")
    assert uses_property_folder("buildings", "Hausratversicherung")
    assert not uses_property_folder("buildings", "Kfz-Haftpflichtversicherung für S-AB 123")
