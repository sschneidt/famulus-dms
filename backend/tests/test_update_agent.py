"""scripts/update-agent.sh - mit einem vorgetaeuschten "docker", ohne echtes Docker.

Der Helfer laeuft mit hohen Rechten (Aufgabenplaner der Synology), seine Eingabe kommt aus der Anwendung. Deshalb
wird hier vor allem geprueft, dass er bei unsauberer Eingabe nichts tut und bei Fehlern den alten Stand behaelt.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "update-agent.sh"
IMAGE = "ghcr.io/sschneidt/famulus-dms"


def find_sh() -> str | None:
    found = shutil.which("sh")
    if found and "system32" not in found.lower():
        return found
    for candidate in (r"C:\Program Files\Git\bin\sh.exe", r"C:\Program Files\Git\usr\bin\sh.exe"):
        if Path(candidate).is_file():
            return candidate
    return None


SH = find_sh()
pytestmark = pytest.mark.skipif(SH is None, reason="keine POSIX-Shell (sh) gefunden")

# Vorgetaeuschtes docker: schreibt jeden Aufruf in calls.log; "Laufendes Image" ist das, was in der Compose-Datei steht,
# sobald "compose up" lief. PULL_FAILS / UNHEALTHY steuern die Fehlerfaelle.
FAKE_DOCKER = r"""#!/bin/sh
echo "$*" >> "$FAKE_DIR/calls.log"
case "$1" in
  pull) [ -n "$PULL_FAILS" ] && exit 1; exit 0 ;;
  ps) echo abc123 ;;
  compose)
    case "$2" in
      version) exit 0 ;;
    esac
    f=""
    while [ $# -gt 0 ]; do [ "$1" = "-f" ] && f="$2"; shift; done
    grep -o "$FAKE_IMAGE:[0-9.]*" "$f" | head -n 1 > "$FAKE_DIR/running"
    ;;
  inspect)
    case "$*" in
      *config_files*) echo "$FAKE_COMPOSE" ;;
      *Config.Image*) cat "$FAKE_DIR/running" ;;
      *Health*) if [ -n "$UNHEALTHY" ]; then echo starting; else echo healthy; fi ;;
    esac ;;
esac
exit 0
"""


@pytest.fixture
def env(tmp_path):
    folder = tmp_path / "backups"
    folder.mkdir()
    fake = tmp_path / "fake"
    fake.mkdir()
    docker = fake / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8", newline="\n")
    docker.chmod(0o755)
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(
        f"services:\n  app-api:\n    image: {IMAGE}:0.2.4\n  app-worker:\n    image: {IMAGE}:0.2.4\n  db:\n    image: pgvector/pgvector:pg16\n",
        encoding="utf-8", newline="\n",
    )
    (fake / "running").write_text(f"{IMAGE}:0.2.4\n", encoding="utf-8")
    variables = {
        **os.environ,
        "PATH": f"{fake.as_posix()}{os.pathsep}{os.environ['PATH']}",
        "UPDATE_DIR": folder.as_posix(), "COMPOSE_FILE": compose.as_posix(), "FAKE_COMPOSE": compose.as_posix(),
        "FAKE_DIR": fake.as_posix(), "FAKE_IMAGE": IMAGE, "TMPDIR": tmp_path.as_posix(),
        "HEALTH_WAIT": "2", "HEALTH_POLL": "1",
    }
    return type("Env", (), {"folder": folder, "compose": compose, "fake": fake, "vars": variables})


def run(env, **extra):
    return subprocess.run([SH, str(SCRIPT)], env={**env.vars, **extra}, capture_output=True, text=True, timeout=60)


def status(env) -> dict:
    return json.loads((env.folder / "update-status.json").read_text(encoding="utf-8"))


def calls(env) -> str:
    log = env.fake / "calls.log"
    return log.read_text(encoding="utf-8") if log.exists() else ""


def test_ohne_anforderung_gibt_es_nur_ein_lebenszeichen(env):
    result = run(env)
    assert result.returncode == 0, result.stderr
    assert (env.folder / "update-agent.txt").read_text().strip().isdigit()
    assert not (env.folder / "update-status.json").exists()
    assert calls(env) == ""


def test_update_klappt(env):
    (env.folder / "update-request.txt").write_text("version=0.3.0\n", encoding="utf-8")
    result = run(env)
    assert result.returncode == 0, result.stderr
    assert status(env)["state"] == "done" and status(env)["version"] == "0.3.0"
    assert f"{IMAGE}:0.3.0" in env.compose.read_text(encoding="utf-8")
    assert "pgvector/pgvector:pg16" in env.compose.read_text(encoding="utf-8")  # fremde Images bleiben
    assert f"{IMAGE}:0.2.4" in env.compose.with_name(env.compose.name + ".vorher").read_text(encoding="utf-8")
    assert not (env.folder / "update-request.txt").exists()  # nur einmal ausfuehren
    assert f"pull {IMAGE}:0.3.0" in calls(env)
    assert "up -d app-api app-worker" in calls(env)


def test_image_nicht_ladbar_veraendert_nichts(env):
    before = env.compose.read_text(encoding="utf-8")
    (env.folder / "update-request.txt").write_text("version=0.3.0\n", encoding="utf-8")
    run(env, PULL_FAILS="1")
    assert status(env)["state"] == "failed"
    assert env.compose.read_text(encoding="utf-8") == before
    assert "up -d" not in calls(env)


def test_nicht_gesunde_version_wird_zurueckgesetzt(env):
    before = env.compose.read_text(encoding="utf-8")
    (env.folder / "update-request.txt").write_text("version=0.3.0\n", encoding="utf-8")
    run(env, UNHEALTHY="1")
    assert status(env)["state"] == "rolled_back"
    assert env.compose.read_text(encoding="utf-8") == before
    assert calls(env).count("up -d app-api app-worker") == 2  # neu, dann wieder alt


@pytest.mark.parametrize("content", [
    "version=0.3.0; rm -rf /\n",
    "version=$(touch /tmp/x)\n",
    "version=../../etc\n",
    "version=latest\n",
    "version=1.2\n",
    "image=evil/image:1.0.0\nversion=\n",
    "",
])
def test_unsaubere_anforderung_wird_abgelehnt(env, content):
    before = env.compose.read_text(encoding="utf-8")
    (env.folder / "update-request.txt").write_text(content, encoding="utf-8")
    result = run(env)
    assert result.returncode == 0
    assert status(env)["state"] == "failed"
    assert env.compose.read_text(encoding="utf-8") == before
    assert "pull" not in calls(env)


def test_gesperrt_waehrend_ein_anderer_lauf_arbeitet(env, tmp_path):
    (tmp_path / "famulus-update.lock").mkdir()
    (env.folder / "update-request.txt").write_text("version=0.3.0\n", encoding="utf-8")
    run(env)
    assert (env.folder / "update-request.txt").exists()  # bleibt fuer den naechsten Lauf liegen
    assert calls(env) == ""
