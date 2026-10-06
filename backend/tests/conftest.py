"""Gemeinsame Fixtures. Diese Tests brauchen keine laufende Postgres-Instanz -
sie pruefen App-Aufbau, Routing und die reinen Sicherheits-Bausteine (Hashing/JWT).
Endpunkte, die tatsaechlich eine DB-Session ausfuehren (setup/bootstrap, auth/*,
categories/*), sind bewusst nicht hier getestet - das braucht docker compose up (db)
bzw. eine echte Postgres-Verbindung und folgt in einer spaeteren Iteration
(siehe README.md, Abschnitt "Tests").
"""
import os

import pytest
from fastapi.testclient import TestClient

from homedms.config import get_settings
from homedms.main import app
from homedms.runtime import find_tesseract


def pytest_configure(config):
    config.addinivalue_line("markers", "needs_tesseract: braucht das Programm Tesseract (Texterkennung)")


def pytest_collection_modifyitems(config, items):
    """Tests mit echtem Tesseract brauchen es auch wirklich. Fehlt es, heisst das Ergebnis "nicht
    geprueft" - deshalb gilt:
    - In der CI (CI=true) und mit HOMEDMS_REQUIRE_TESSERACT=1 wird NICHT uebersprungen: Die Tests
      schlagen fehl, ein fehlendes Tesseract faellt also immer auf.
    - Sonst (Entwicklungsrechner ohne Installation) werden sie mit deutlichem Hinweis uebersprungen."""
    if find_tesseract(get_settings().tesseract_cmd):
        return
    if os.environ.get("CI") or os.environ.get("HOMEDMS_REQUIRE_TESSERACT") == "1":
        return
    skip = pytest.mark.skip(reason="NICHT GEPRUEFT: Tesseract ist nicht installiert (Windows: winget install UB-Mannheim.TesseractOCR)")
    for item in items:
        if "needs_tesseract" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
