"""Eigener tessdata-Ordner (homedms/core/ocr_languages.py): Er wird ueber TESSDATA_PREFIX bekannt gemacht.

Frueher stand er als `--tessdata-dir "..."` in der pytesseract-Konfiguration. Unter Windows bleiben die
Anfuehrungszeichen dabei im Pfad - Tesseract fand keine Sprachdaten ("Error opening data file")."""
import os

import pytest

from homedms.config import get_settings
from homedms.core import ocr_languages


@pytest.fixture
def own_dir(tmp_path, monkeypatch):
    folder = tmp_path / "mit Leerzeichen" / "tessdata"  # Leerzeichen wie in "C:\Program Files"
    folder.mkdir(parents=True)
    monkeypatch.setattr(get_settings(), "tessdata_dir", str(folder))
    monkeypatch.setenv("TESSDATA_PREFIX", "vorher")  # setenv + Rueckgabe: monkeypatch stellt den Wert am Ende wieder her
    return folder


def test_config_enthaelt_keine_anfuehrungszeichen(own_dir):
    (own_dir / "eng.traineddata").write_bytes(b"x")
    config = ocr_languages.tesseract_config()
    assert config == ""
    assert '"' not in config and "tessdata-dir" not in config


def test_eigener_ordner_wird_ueber_umgebungsvariable_gesetzt(own_dir):
    (own_dir / "eng.traineddata").write_bytes(b"x")
    ocr_languages.tesseract_config()
    assert os.environ["TESSDATA_PREFIX"] == str(own_dir.resolve())


def test_leerer_ordner_aendert_nichts(own_dir):
    ocr_languages.tesseract_config()
    assert os.environ["TESSDATA_PREFIX"] == "vorher"
    assert ocr_languages.use_own_tessdata() is False
