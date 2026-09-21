"""Gemeinsame Fixtures. Diese Tests brauchen keine laufende Postgres-Instanz -
sie pruefen App-Aufbau, Routing und die reinen Sicherheits-Bausteine (Hashing/JWT).
Endpunkte, die tatsaechlich eine DB-Session ausfuehren (setup/bootstrap, auth/*,
categories/*), sind bewusst nicht hier getestet - das braucht docker compose up (db)
bzw. eine echte Postgres-Verbindung und folgt in einer spaeteren Iteration
(siehe README.md, Abschnitt "Tests").
"""
import pytest
from fastapi.testclient import TestClient

from homedms.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
