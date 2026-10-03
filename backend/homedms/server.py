"""HomeDMS ohne Docker starten - ein Befehl fuer Windows-PC und Linux-Server.

    python -m homedms.server            (aus dem Ordner backend/, mit dessen .venv)

Was sonst docker-compose erledigt, macht dieser Starter selbst:
1. Einstellungen aus der Datei homedms.env laden (im HomeDMS-Hauptordner; andere Datei:
   Umgebungsvariable HOMEDMS_ENV). Vorlage: homedms.env.example.
2. Datenbank auf den neuesten Stand bringen (alembic upgrade head) und Dateien aus aelteren
   Versionen zur Ablage einreihen - wie docker-entrypoint.sh.
3. Optional Meilisearch mitstarten (MEILISEARCH_BINARY = Pfad zur meilisearch(.exe)).
4. Den Worker (Texterkennung, KI, Ablage, Scan-Ordner) als zweiten Prozess starten - und neu
   starten, falls er abstuerzt.
5. Die Weboberflaeche + API auf HOST:PORT bereitstellen (Standard 0.0.0.0:8000).

Beenden mit Strg+C (bzw. Dienst stoppen) beendet auch Worker und Meilisearch.
Installation und Dienst-Einrichtung: scripts/install-linux.sh, scripts/install-windows.ps1,
Anleitung in docs/Installation-ohne-Docker.md.
"""
import argparse
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BACKEND_DIR.parent

logger = logging.getLogger("homedms.server")


def load_env_file() -> Path | None:
    """homedms.env laden. Bereits gesetzte Umgebungsvariablen haben Vorrang."""
    from dotenv import load_dotenv

    path = Path(os.environ.get("HOMEDMS_ENV") or ROOT_DIR / "homedms.env")
    if path.is_file():
        load_dotenv(path, override=False)
        return path
    return None


class Child:
    """Ein Hilfsprozess (Worker, Meilisearch), der bei einem Absturz neu gestartet wird."""

    def __init__(self, name: str, args: list[str], cwd: Path, log_file: Path | None = None) -> None:
        self.name, self.args, self.cwd, self.log_file = name, args, cwd, log_file
        self.process: subprocess.Popen | None = None
        self.stopping = False
        self.thread = threading.Thread(target=self._watch, name=name, daemon=True)

    def start(self) -> None:
        self._spawn()
        self.thread.start()

    def _spawn(self) -> None:
        logger.info("Starte %s", self.name)
        output = open(self.log_file, "ab") if self.log_file else None  # noqa: SIM115 - lebt mit dem Prozess
        self.process = subprocess.Popen(self.args, cwd=self.cwd, stdout=output, stderr=subprocess.STDOUT if output else None)

    def _watch(self) -> None:
        delay = 2.0
        while not self.stopping:
            code = self.process.wait() if self.process else 0
            if self.stopping:
                return
            logger.error("%s wurde beendet (Code %s) - Neustart in %.0f s", self.name, code, delay)
            time.sleep(delay)
            delay = min(delay * 2, 60)
            if not self.stopping:
                self._spawn()

    def stop(self) -> None:
        self.stopping = True
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.process.kill()


def migrate() -> None:
    from alembic import command
    from alembic.config import Config

    logger.info("Datenbank wird auf den neuesten Stand gebracht (alembic upgrade head) ...")
    command.upgrade(Config(str(BACKEND_DIR / "alembic.ini")), "head")


async def _refile() -> None:
    from homedms.cli import refile_all
    from homedms.db import engine

    try:
        await refile_all()
    finally:
        await engine.dispose()  # Verbindungen gehoeren zu diesem Event-Loop - der Webserver startet einen neuen


def check_environment() -> list[str]:
    """Hinweise auf fehlende Bausteine - der Start geht trotzdem weiter."""
    from homedms.config import get_settings
    from homedms.runtime import find_tesseract

    settings = get_settings()
    problems = []
    if not find_tesseract(settings.tesseract_cmd):
        problems.append("Tesseract nicht gefunden - Texterkennung von Scans/Fotos geht nicht (TESSERACT_CMD setzen)")
    if not Path(settings.frontend_dist).joinpath("index.html").is_file():
        problems.append(f"Weboberflaeche fehlt ({settings.frontend_dist}) - nur die API laeuft")
    if settings.jwt_secret.startswith("dev-only"):
        problems.append("JWT_SECRET ist nicht gesetzt - bitte in homedms.env eintragen")
    for name in ("documents_path", "scan_path"):
        Path(getattr(settings, name)).mkdir(parents=True, exist_ok=True)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m homedms.server", description="HomeDMS ohne Docker starten")
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--no-worker", action="store_true", help="nur Weboberflaeche/API (Worker laeuft anderswo)")
    parser.add_argument("--no-migrate", action="store_true", help="Datenbank-Migrationen ueberspringen")
    args = parser.parse_args(argv)

    env_file = load_env_file()  # zuerst - LOG_DIR kann in homedms.env stehen
    from homedms.runtime import setup_logging

    log_file = setup_logging("homedms")
    os.chdir(BACKEND_DIR)  # relative Pfade (frontend/dist, data/...) beziehen sich auf backend/
    logger.info("Einstellungen: %s", env_file or "nur Umgebungsvariablen (keine homedms.env gefunden)")
    if log_file:
        logger.info("Protokoll: %s", log_file)

    for problem in check_environment():
        logger.warning(problem)
    if not args.no_migrate:
        migrate()
        setup_logging("homedms")  # alembic.ini stellt das Protokoll auf WARN um - zuruecksetzen
        from homedms.runtime import run

        try:
            run(_refile())
        except Exception:  # noqa: BLE001 - wie docker-entrypoint.sh: Start nicht verhindern
            logger.exception("Ablage konnte nicht eingereiht werden - weiter ohne")

    from homedms.runtime import bind_children_to_this_process

    bind_children_to_this_process()  # Windows: Worker/Meilisearch enden sicher mit dem Starter
    children: list[Child] = []
    meili_binary = os.environ.get("MEILISEARCH_BINARY", "")
    if meili_binary:
        from homedms.config import get_settings

        settings = get_settings()
        address = settings.meilisearch_url.split("://", 1)[-1].rstrip("/") or "127.0.0.1:7700"
        data = Path(os.environ.get("MEILISEARCH_DATA", ROOT_DIR / "data" / "meilisearch"))
        data.mkdir(parents=True, exist_ok=True)
        children.append(Child("Meilisearch", [
            meili_binary, "--db-path", str(data / "data.ms"), "--dump-dir", str(data / "dumps"),
            "--http-addr", address, "--master-key", settings.meilisearch_key, "--env", "production",
            "--no-analytics", "--log-level", "WARN",
        ], cwd=data, log_file=log_file.with_name("meilisearch.log") if log_file else None))
    if not args.no_worker:
        children.append(Child("Worker", [sys.executable, "-m", "homedms.worker"], cwd=BACKEND_DIR))
    for child in children:
        child.start()

    import uvicorn

    from homedms.runtime import run

    # log_config=None: uvicorn schreibt ueber das hier eingerichtete Protokoll (Konsole/LOG_DIR)
    server = uvicorn.Server(uvicorn.Config(
        "homedms.main:app", host=args.host, port=args.port, proxy_headers=True, log_config=None,
    ))
    logger.info("HomeDMS laeuft auf http://%s:%s", "localhost" if args.host == "0.0.0.0" else args.host, args.port)
    try:
        run(server.serve())
    except KeyboardInterrupt:
        pass
    finally:
        for child in reversed(children):
            child.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
