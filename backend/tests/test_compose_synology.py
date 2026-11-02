"""docker-compose.synology.yml (eine Datei fuer den Container Manager) muss zu docker-compose.yml passen.

Die Synology-Datei steht allein, ohne .env und ohne Quellcode. Dieser Test sorgt dafuer, dass sie nicht
unbemerkt vom Haupt-Stack abweicht (Dienste, Images, Ports) und nichts verlangt, was ein Anwender nicht hat."""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
MAIN = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
SYNOLOGY_TEXT = (ROOT / "docker-compose.synology.yml").read_text(encoding="utf-8")
SYNOLOGY = yaml.safe_load(SYNOLOGY_TEXT)


def test_gleiche_dienste_und_projektname():
    assert set(SYNOLOGY["services"]) == set(MAIN["services"])
    assert SYNOLOGY["name"] == MAIN["name"] == "homedms"  # sonst waeren die Datenvolumes "weg"


def test_gleiche_volumes_plus_schluesselvolume():
    assert set(SYNOLOGY["volumes"]) - set(MAIN["volumes"]) == {"appdata"}
    assert set(MAIN["volumes"]) <= set(SYNOLOGY["volumes"])


@pytest.mark.parametrize("service", ["db", "meilisearch", "ollama", "ollama-init"])
def test_fremde_images_gleich(service):
    assert SYNOLOGY["services"][service]["image"] == MAIN["services"][service]["image"]


@pytest.mark.parametrize("service", ["app-api", "app-worker"])
def test_eigenes_image_aus_der_registry_ohne_bauen(service):
    spec = SYNOLOGY["services"][service]
    assert spec["image"].startswith("ghcr.io/sschneidt/famulus-dms:")
    assert "build" not in spec, "ohne Quellcode neben der Datei kann der Container Manager nichts bauen"


def test_keine_pflichtvariablen_und_keine_relativen_dateien():
    """Ohne .env duerfen keine ${NAME:?...} und keine Pfade wie ./init/... vorkommen."""
    assert not re.search(r"\$\{\w+:\?", SYNOLOGY_TEXT)
    for name, spec in SYNOLOGY["services"].items():
        for volume in spec.get("volumes", []):
            source = volume.split(":")[0]
            assert not source.startswith("."), f"{name}: relativer Pfad {volume}"


def test_nach_aussen_nur_die_zwei_app_ports():
    published = {n: s["ports"] for n, s in SYNOLOGY["services"].items() if "ports" in s}
    assert list(published) == ["app-api"]
    assert sorted(published["app-api"]) == ["8000:8000", "8443:8443"]


@pytest.mark.parametrize("service", ["app-api", "app-worker"])
def test_schluesseldatei_statt_festem_jwt_secret(service):
    env = SYNOLOGY["services"][service]["environment"]
    assert env["JWT_SECRET_FILE"] == "/data/appdata/jwt_secret" and "JWT_SECRET" not in env
    assert any(v.startswith("appdata:") for v in SYNOLOGY["services"][service]["volumes"])


def test_api_und_worker_sind_sich_in_den_gemeinsamen_einstellungen_einig():
    api, worker = (SYNOLOGY["services"][n]["environment"] for n in ("app-api", "app-worker"))
    for key in ("DATABASE_URL", "MEILISEARCH_URL", "MEILISEARCH_KEY", "OLLAMA_URL", "OLLAMA_CHAT_MODEL",
                "OLLAMA_EMBEDDING_MODEL", "DOCUMENTS_PATH", "JWT_SECRET_FILE", "OCR_LANGUAGES", "TESSDATA_DIR", "TZ"):
        assert api[key] == worker[key], key


def test_datenbank_passwort_stimmt_ueberein():
    db = SYNOLOGY["services"]["db"]["environment"]
    url = SYNOLOGY["services"]["app-api"]["environment"]["DATABASE_URL"]
    assert url == f"postgresql://{db['POSTGRES_USER']}:{db['POSTGRES_PASSWORD']}@db:5432/{db['POSTGRES_DB']}"
    assert SYNOLOGY["services"]["meilisearch"]["environment"]["MEILI_MASTER_KEY"] == \
        SYNOLOGY["services"]["app-api"]["environment"]["MEILISEARCH_KEY"]


def test_ordner_der_nas_stehen_an_allen_noetigen_stellen_gleich():
    """Alle Pfade beginnen mit demselben Ordner - "Suchen und Ersetzen" in der Anleitung klappt dann."""
    paths = set(re.findall(r"(/volume\d+/\w+)", SYNOLOGY_TEXT))
    assert paths == {"/volume1/famulus"}
