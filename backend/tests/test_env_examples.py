"""Beispiel-Konfigurationen in mehreren Sprachen (.env.example, homedms.env.example und die Varianten
.env.de.example, .env.ru.example, homedms.env.de.example, ...).

Nur die Kommentare duerfen sich unterscheiden: Dieselben Schluessel mit denselben Werten in jeder Sprache -
sonst haette eine Sprache eine andere Einstellung als die andere."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LANGS = ("en", "de", "ru")
# Familie -> Dateiname je Sprache (Englisch ist die Standarddatei ohne Sprachkuerzel)
FAMILIES = {".env": ".env.{}example", "homedms.env": "homedms.env.{}example"}
LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*?)(?:\s+#.*)?$")


def path_of(family: str, lang: str) -> Path:
    return ROOT / FAMILIES[family].format("" if lang == "en" else f"{lang}.")


def values(path: Path) -> dict[str, str]:
    """Schluessel -> Wert (ohne Kommentar am Zeilenende)."""
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and (m := LINE.match(line)):
            result[m.group(1)] = m.group(2).strip()
    return result


FAMILY_LANG = [(family, lang) for family in FAMILIES for lang in LANGS]
FAMILY_TRANSLATED = [(family, lang) for family in FAMILIES for lang in ("de", "ru")]


@pytest.mark.parametrize(("family", "lang"), FAMILY_LANG)
def test_datei_existiert_und_ist_utf8_ohne_bom(family, lang):
    data = path_of(family, lang).read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf"), "ein BOM wuerde den ersten Schluessel beschaedigen"
    data.decode("utf-8")
    assert len(values(path_of(family, lang))) > 10


@pytest.mark.parametrize(("family", "lang"), FAMILY_TRANSLATED)
def test_gleiche_schluessel_und_werte_wie_englisch(family, lang):
    english, other = values(path_of(family, "en")), values(path_of(family, lang))
    assert sorted(english.keys() - other.keys()) == [], f"{lang}: fehlende Schluessel"
    assert sorted(other.keys() - english.keys()) == [], f"{lang}: zusaetzliche Schluessel"
    assert {k: (english[k], other[k]) for k in english if english[k] != other[k]} == {}


@pytest.mark.parametrize(("family", "lang"), FAMILY_TRANSLATED)
def test_kommentare_sind_wirklich_uebersetzt(family, lang):
    """Eine Datei, die noch dem englischen Original gleicht (nur Kommentare), wurde vermutlich nicht uebersetzt."""
    english = path_of(family, "en").read_text(encoding="utf-8").splitlines()
    comments = [line for line in path_of(family, lang).read_text(encoding="utf-8").splitlines() if line.lstrip().startswith("#")]
    same = [c for c in comments if c in english and len(c) > 25]
    assert len(same) <= 3, same


def test_docker_pflichtvariablen_stehen_in_der_vorlage():
    """docker-compose.yml verlangt diese Variablen (${NAME:?...}) - sie muessen in jeder .env-Vorlage stehen."""
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    required = set(re.findall(r"\$\{(\w+):\?", compose))
    assert required >= {"POSTGRES_PASSWORD", "MEILI_MASTER_KEY", "JWT_SECRET"}
    for lang in LANGS:
        assert required <= values(path_of(".env", lang)).keys(), lang


def test_vorlagen_enthalten_keine_echten_geheimnisse():
    for family in FAMILIES:
        for lang in LANGS:
            data = values(path_of(family, lang))
            for key in ("POSTGRES_PASSWORD", "MEILI_MASTER_KEY", "JWT_SECRET", "MEILISEARCH_KEY"):
                if key in data:
                    assert "CHANGE_ME" in data[key], f"{path_of(family, lang).name}: {key} muss ein Platzhalter sein"
    assert "CHANGE_ME" in values(path_of("homedms.env", "en"))["DATABASE_URL"]


# Diese Schluessel ersetzen die Installationsskripte in homedms.env (sed bzw. Regex) - sie muessen in jeder Vorlage stehen
INSTALLER_KEYS = {"DATABASE_URL", "OLLAMA_URL", "JWT_SECRET", "MEILISEARCH_KEY", "DOCUMENTS_PATH", "SCAN_PATH", "LOG_DIR",
                  "MEILISEARCH_DATA", "TESSERACT_CMD", "PORT", "HTTPS_PORT", "TLS_DIR", "TESSDATA_DIR", "SETUP_CODE",
                  "MEILISEARCH_BINARY", "MEILISEARCH_URL"}


@pytest.mark.parametrize("lang", LANGS)
def test_installer_findet_alle_schluessel(lang):
    assert INSTALLER_KEYS <= values(path_of("homedms.env", lang)).keys()


def test_installer_waehlen_die_vorlage_nach_sprache():
    windows = (ROOT / "scripts" / "install-windows.ps1").read_text(encoding="utf-8")
    linux = (ROOT / "scripts" / "install-linux.sh").read_text(encoding="utf-8")
    assert 'homedms.env.$(Get-InstallerLanguage $Language).example' in windows
    assert "ReadAllText($template, [Text.Encoding]::UTF8)" in windows        # nicht als ANSI lesen
    assert 'homedms.env.$(i18n_language).example' in linux
