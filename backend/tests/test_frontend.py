"""Auslieferung der Weboberflaeche (homedms/frontend.py)."""
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from homedms.frontend import mount_frontend


@pytest.fixture
def dist(tmp_path: Path) -> Path:
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text("<!doctype html><title>Famulus DMS</title>")
    (root / "assets" / "index-abc123.js").write_text("console.log(1)")
    (root / "sw.js").write_text("// sw")
    (tmp_path / "geheim.txt").write_text("nicht ausliefern")
    return root


def make_app(dist_dir: Path) -> TestClient:
    app = FastAPI()
    router = APIRouter(prefix="/api/v1")

    @router.get("/ping")
    async def ping() -> dict:
        return {"pong": True}

    app.include_router(router)
    assert mount_frontend(app, dist_dir) is True
    return TestClient(app)


def test_index_und_spa_routen(dist: Path) -> None:
    client = make_app(dist)
    for path in ("/", "/dokumente/123", "/termine?ansicht=erledigt"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "<title>Famulus DMS</title>" in resp.text
        assert resp.headers["cache-control"] == "no-cache"


def test_assets_mit_langem_cache(dist: Path) -> None:
    client = make_app(dist)
    resp = client.get("/assets/index-abc123.js")
    assert resp.status_code == 200
    assert resp.text == "console.log(1)"
    assert "immutable" in resp.headers["cache-control"]
    assert client.get("/sw.js").headers["cache-control"] == "no-cache"
    assert client.get("/assets/fehlt.js").status_code == 404


def test_api_bleibt_api(dist: Path) -> None:
    client = make_app(dist)
    assert client.get("/api/v1/ping").json() == {"pong": True}
    for path in ("/api/v1/gibtsnicht", "/api", "/health/x", "/docs/x"):
        resp = client.get(path)
        assert resp.status_code == 404, path
        assert "Famulus DMS" not in resp.text


def test_kein_zugriff_ausserhalb_des_build_ordners(dist: Path) -> None:
    client = make_app(dist)
    for path in ("/../geheim.txt", "/%2e%2e/geheim.txt", "/assets/../../geheim.txt"):
        assert "nicht ausliefern" not in client.get(path).text, path


def test_ohne_build_nur_api(tmp_path: Path) -> None:
    app = FastAPI()
    assert mount_frontend(app, tmp_path / "gibtsnicht") is False
    assert TestClient(app).get("/").status_code == 404
