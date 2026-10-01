"""Automatische Benennung und Ablagepfade (homedms/core/naming.py)."""
from datetime import date
from pathlib import PurePosixPath

import pytest

from homedms.core.naming import (
    auto_title,
    clean_subject,
    file_basename,
    relative_path,
    safe_part,
    with_counter,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Rechnung Wasserschaden-Reparatur", "Rechnung Wasserschaden-Reparatur"),
        ('  "Stromrechnung\n August"  ', "Stromrechnung August"),
        ("„Beitragsanpassung 2027“.", "Beitragsanpassung 2027"),
        ("", None),
        (None, None),
        ("ab", None),
    ],
)
def test_clean_subject(raw, expected):
    assert clean_subject(raw) == expected


def test_clean_subject_kuerzt_an_wortgrenze():
    subject = clean_subject("Rechnung " + "sehr " * 30 + "lang")
    assert subject is not None and len(subject) <= 80
    assert not subject.endswith("seh")
    assert subject.split()[-1] == "sehr"


@pytest.mark.parametrize(
    ("subject", "issuer", "expected"),
    [
        ("Rechnung Wasserschaden-Reparatur", "Sanitär Müller GmbH", "Rechnung Wasserschaden-Reparatur – Sanitär Müller GmbH"),
        ("Stadtwerke Musterstadt Stromrechnung", "Stadtwerke Musterstadt", "Stadtwerke Musterstadt Stromrechnung"),
        ("Kontoauszug September", None, "Kontoauszug September"),
        (None, "Finanzamt Stuttgart", "Finanzamt Stuttgart"),
        (None, None, None),
        ("", "  ", None),
    ],
)
def test_auto_title(subject, issuer, expected):
    assert auto_title(subject, issuer) == expected


def test_file_basename_datum_absender_betreff():
    assert (
        file_basename(date(2026, 9, 12), "Sanitär Müller GmbH", "Rechnung Wasserschaden-Reparatur", "x")
        == "2026-09-12 Sanitär Müller GmbH – Rechnung Wasserschaden-Reparatur"
    )


def test_file_basename_fallbacks():
    assert file_basename(None, None, "Kontoauszug", "x") == "Kontoauszug"
    assert file_basename(date(2026, 1, 2), "Finanzamt", None, "x") == "2026-01-02 Finanzamt"
    # ohne erkannte Daten: Titel ohne Datei-Endung (die kommt separat dazu)
    assert file_basename(None, None, None, "ScannedDocument1.pdf") == "ScannedDocument1"
    assert file_basename(None, None, None, "") == "Dokument"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('Rechnung 12/2026: "Heizung"', "Rechnung 12 2026 Heizung"),
        ("Bericht...", "Bericht"),
        ("CON", "_CON"),
        ("nul.txt", "_nul.txt"),
        ("a\tb\nc", "a b c"),
        ("  ", "Dokument"),
        ("..\\..\\etc", "etc"),
    ],
)
def test_safe_part(raw, expected):
    assert safe_part(raw) == expected


def test_safe_part_keine_pfadtrenner():
    for evil in ("../../etc/passwd", "a/b\\c", "..", "."):
        part = safe_part(evil)
        assert "/" not in part and "\\" not in part and part not in ("..", ".")


def test_relative_path():
    base = "2026-09-12 Sanitär Müller GmbH – Rechnung"
    assert relative_path("Familie Muster", "Haus & Reparaturen", 2026, base, ".PDF") == PurePosixPath(
        "Familie Muster/Haus & Reparaturen/2026/2026-09-12 Sanitär Müller GmbH – Rechnung.pdf"
    )
    assert relative_path("Familie Muster", None, 2026, base, ".pdf").parts[1] == "_Unsortiert"
    assert relative_path("Familie Muster", "Steuern", 2026, base, ".pdf", trashed=True) == PurePosixPath(
        f"Familie Muster/_Papierkorb/{base}.pdf"
    )
    assert relative_path("F", "K", 2026, "Brief", ".png", page=2).name == "Brief - Seite 2.png"
    # Kategorie- oder Haushaltsname mit Schraegstrich darf keine Unterordner erzeugen
    assert relative_path("A/B", "Bank/Finanzen", 2026, "x", ".pdf").parts[:2] == ("A B", "Bank Finanzen")


def test_with_counter():
    assert with_counter(PurePosixPath("a/b/Name.pdf"), 2) == PurePosixPath("a/b/Name (2).pdf")


def test_relative_path_mit_objektordner():
    assert relative_path("F", "Haus & Reparaturen", 2026, "x", ".pdf", subfolder="Stuttgart Musterstraße 5") == PurePosixPath(
        "F/Haus & Reparaturen/Stuttgart Musterstraße 5/2026/x.pdf"
    )
    # ohne Kategorie bzw. im Papierkorb spielt der Objektordner keine Rolle
    assert relative_path("F", None, 2026, "x", ".pdf", subfolder="S").parts[1:3] == ("_Unsortiert", "2026")
    assert relative_path("F", "K", 2026, "x", ".pdf", subfolder="S", trashed=True).parts[1] == "_Papierkorb"
    assert relative_path("F", "K", 2026, "x", ".pdf", subfolder="A/B").parts[2] == "A B"
