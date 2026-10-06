"""App-Aufbau/Routing: prueft, dass alle bisher implementierten Endpunkte unter dem
richtigen Prefix registriert sind (siehe docs/API-Design.md). Geht ueber das
OpenAPI-Schema statt ueber app.routes direkt, damit das robust gegenueber internen
FastAPI-Routing-Implementierungsdetails bleibt. Reine Struktur-Pruefung - ruft keinen
Endpunkt tatsaechlich auf (dafuer waere teils eine DB noetig).
"""
from homedms.main import app


def _openapi_paths() -> set[str]:
    return set(app.openapi()["paths"].keys())


def test_health_route_is_unprefixed():
    assert "/health" in _openapi_paths()


def test_expected_api_v1_routes_registered():
    paths = _openapi_paths()
    expected = {
        "/api/v1/setup/status",
        "/api/v1/setup/bootstrap",
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/categories",
        "/api/v1/documents",
        "/api/v1/documents/needs-review",
        "/api/v1/documents/trash",
        "/api/v1/documents/{document_id}",
        "/api/v1/documents/{document_id}/download",
        "/api/v1/documents/{document_id}/restore",
    }
    missing = expected - paths
    assert not missing, f"Fehlende Routen: {missing}"


def test_openapi_schema_builds():
    # Zieht implizit alle Pydantic-Schemas/Response-Models durch - schlaegt fehl,
    # wenn irgendwo ein kaputtes Modell/eine kaputte Typ-Annotation steckt.
    schema = app.openapi()
    assert schema["info"]["title"] == "Famulus DMS API"
