"""Mehrsprachigkeit des Servers: Kataloge vollstaendig, Platzhalter stimmen, Sprachwahl (homedms/i18n)."""
import ast
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from homedms import i18n
from homedms.i18n import _, _n, translate_stored, use_language

PACKAGE = Path(i18n.__file__).parent.parent
PLACEHOLDER = re.compile(r"\{(\w+)\}")
FORMS = {"en": 2, "ru": 3}


def _marked() -> tuple[set[str], set[str]]:
    """Alle mit _(), N_() bzw. _n() markierten deutschen Texte (einzeln, Mehrzahl-Schluessel)."""
    singles, plurals = set(), set()
    for path in PACKAGE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text("utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else None
            args = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if name in ("_", "N_", "gettext") and args:
                singles.add(args[0])
            elif name in ("_n", "ngettext") and len(args) >= 2:
                plurals.add(args[1])
    return singles, plurals


SINGLES, PLURALS = _marked()


def test_texte_gefunden():
    assert len(SINGLES) > 200 and len(PLURALS) > 10
    assert "Dokument nicht gefunden" in SINGLES and "Rechnungen" in SINGLES


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_katalog_vollstaendig(lang):
    catalog = i18n.catalog(lang)
    assert sorted(t for t in SINGLES if not isinstance(catalog.get(t), str) or not catalog[t]) == []
    wrong = sorted(t for t in PLURALS if not isinstance(catalog.get(t), list) or len(catalog[t]) != FORMS[lang])
    assert wrong == []


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_platzhalter_stimmen(lang):
    wrong = []
    for key, value in i18n.catalog(lang).items():
        expected = set(PLACEHOLDER.findall(key))
        for form in value if isinstance(value, list) else [value]:
            actual = set(PLACEHOLDER.findall(form))
            if isinstance(value, list):  # Mehrzahl: {count} darf in einer Form fehlen ("New suggestion")
                expected, actual = expected - {"count"}, actual - {"count"}
            if actual != expected:
                wrong.append((key, form))
    assert wrong == []


@pytest.mark.parametrize(("header", "lang"), [
    (None, "de"), ("", "de"), ("ru-RU,ru;q=0.9,en;q=0.8", "ru"), ("fr-FR,en;q=0.5,de;q=0.7", "de"),
    ("en-GB", "en"), ("fr,es", "de"), ("de;q=0.1,ru;q=0.2", "ru"), ("en;q=abc,ru", "ru"),
])
def test_accept_language(header, lang):
    assert i18n.from_accept_language(header) == lang


@pytest.mark.parametrize(("n", "index"), [
    (0, 2), (1, 0), (2, 1), (4, 1), (5, 2), (11, 2), (12, 2), (14, 2), (21, 0), (22, 1), (25, 2), (101, 0), (111, 2),
])
def test_russische_mehrzahl(n, index):
    assert i18n.plural_index("ru", n) == index
    assert i18n.plural_index("en", n) == (0 if n == 1 else 1)


def test_uebersetzen_je_sprache():
    assert _("Dokument nicht gefunden") == "Dokument nicht gefunden"
    with use_language("en"):
        assert _("Dokument nicht gefunden") == "Document not found"
        assert _("Test-E-Mail an {email} verschickt.", email="a@b.de") == "Test email sent to a@b.de."
        assert _n("{count} Tag", "{count} Tage", 1) == "1 day"
        assert _n("{count} Tag", "{count} Tage", 3) == "3 days"
        assert _("Ein ganz neuer Text") == "Ein ganz neuer Text"  # unbekannt -> Deutsch
    with use_language("ru"):
        assert [_n("{count} Tag", "{count} Tage", n) for n in (1, 3, 5, 21)] == ["1 день", "3 дня", "5 дней", "21 день"]
    with use_language("xx"):
        assert i18n.current() == "de"


def test_gespeicherte_texte_und_datum():
    with use_language("en"):
        assert translate_stored("Vertraege") == "Contracts"
        assert translate_stored("eigener Text") == "eigener Text"
        assert translate_stored(None) is None
        assert i18n.format_date(date(2026, 10, 5)) == "05/10/2026"
    with use_language("ru"):
        assert translate_stored("Bild nicht lesbar") == "Изображение не читается"
        assert i18n.format_date(date(2026, 10, 5)) == "05.10.2026"


def test_termin_bezeichnung_uebersetzt():
    from homedms.core.reminders import note_label
    note = ("Aufbewahrungsfrist (Steuern, 10 Jahre) endet - Dokument kann danach vernichtet werden. "
            "Das Papier-Original muss bis dahin aufbewahrt werden.")
    with use_language("en"):
        assert note_label("Kündigungsfrist") == "Notice period"
        assert note_label("Mein eigener Termin") == "Mein eigener Termin"
        text = note_label(note)
        assert text.startswith("Retention period (Taxes, 10 years) ends") and text.endswith("kept until then.")
    with use_language("ru"):
        assert "Налоги, 10 лет" in note_label(note)


def test_fehlermeldungen_der_api_in_sprache_des_browsers():
    from homedms.main import app
    client = TestClient(app)
    assert client.get("/api/v1/auth/me", headers={"Accept-Language": "en"}).json()["detail"] == "Not signed in"
    assert client.get("/api/v1/auth/me", headers={"Accept-Language": "ru-RU"}).json()["detail"] == "Вход не выполнен"
    assert client.get("/api/v1/auth/me").json()["detail"] == "Nicht angemeldet"


def test_zertifikatsseite_mehrsprachig(tmp_path):
    from homedms.cert_page import build_redirect_app
    from homedms.core import tls
    from homedms.cert_page_text import BODIES, TITLES
    assert set(BODIES) == set(TITLES) == {"de", "en", "ru"}
    files = tls.ensure_certificates(tmp_path, "nas")
    client = TestClient(build_redirect_app(8443, files), base_url="http://nas:8000")
    page_de = client.get("/zertifikat").text
    page_ru = client.get("/zertifikat", headers={"Accept-Language": "ru"}).text
    page_en = client.get("/zertifikat?lang=en", headers={"Accept-Language": "ru"}).text
    assert 'lang="de"' in page_de and 'lang="ru"' in page_ru and 'lang="en"' in page_en
    assert TITLES["ru"] in page_ru and TITLES["en"] in page_en
    assert files.fingerprint in page_ru and '<a href="?lang=de">Deutsch</a>' in page_en
