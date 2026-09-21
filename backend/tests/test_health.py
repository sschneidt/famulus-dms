"""GET /health - liegt bewusst ausserhalb von /api/v1 (main.py)."""


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
