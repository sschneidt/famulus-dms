"""Diagnose: Zustand aller Bausteine auf einen Blick (Seite "Diagnose", nur Admin).

Nutzerwunsch (03.10.2026): "Reiter Diagnose, wo man den Status der Server usw. sieht und
bestimmte Komponenten evtl. neu starten kann."

Jede Pruefung liefert eine Component mit Ampel (ok/warning/error/disabled), Kurztext, Details,
Hinweis und den passenden Aktionen. Die Pruefungen laufen parallel und haben kurze Zeitlimits -
ein haengender Dienst darf die Seite nicht blockieren. Aktionen fuehrt api/routes/system.py aus.

Bewusst NICHT moeglich: Docker-Container oder Datenbank neu starten - dafuer braeuchte die
Anwendung Zugriff auf den Docker-Dienst des NAS (= volle Kontrolle ueber das Geraet). Der Worker
laesst sich trotzdem neu starten: Er beendet sich selbst, Docker bzw. der Starter (server.py)
startet ihn sofort neu.
"""
import asyncio
import os
import platform
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.config import get_settings

STARTED_AT = time.time()
HEARTBEAT_OK_SECONDS = 60
TASK_LABELS = {
    "ocr_document": "Texterkennung",
    "classify_document": "Einordnung",
    "extract_metadata": "Betreff/Fristen",
    "file_document": "Ablage",
    "scan_folders": "Scan-Ordner",
    "learn_exemplar": "Lernen",
    "pull_model": "KI-Modell laden",
    "restart_worker": "Worker-Neustart",
    "ping": "Test",
    "send_reminders": "Erinnerungen",
}


@dataclass
class Action:
    id: str
    label: str
    confirm: str | None = None  # Rueckfrage vor dem Ausfuehren


@dataclass
class Component:
    key: str
    name: str
    status: str  # ok | warning | error | disabled
    summary: str
    details: list[tuple[str, str]] = field(default_factory=list)
    hint: str | None = None
    actions: list[Action] = field(default_factory=list)


def _size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}".replace(".", ",")
        n /= 1024
    return str(n)


def _duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 90:
        return f"{seconds} s"
    if seconds < 5400:
        return f"{seconds // 60} Min."
    if seconds < 172800:
        return f"{seconds // 3600} Std."
    return f"{seconds // 86400} Tage"


def running_in_docker() -> bool:
    return Path("/.dockerenv").exists() or bool(get_settings().scan_host_path)


# --- einzelne Pruefungen ---------------------------------------------------------------------


async def check_app() -> Component:
    from importlib.metadata import PackageNotFoundError, version

    try:
        app_version = version("homedms")
    except PackageNotFoundError:
        app_version = "0.1.0"
    mode = "Docker" if running_in_docker() else f"ohne Docker ({platform.system()})"
    return Component("app", "HomeDMS", "ok", f"läuft seit {_duration(time.time() - STARTED_AT)}", [
        ("Version", app_version),
        ("Betrieb", mode),
        ("Python", platform.python_version()),
        ("Rechner", platform.node() or "-"),
    ])


async def check_database(db: AsyncSession) -> Component:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    started = time.perf_counter()
    try:
        server = await db.scalar(text("SHOW server_version"))
        size = await db.scalar(text("SELECT pg_database_size(current_database())"))
        revision = await db.scalar(text("SELECT version_num FROM alembic_version"))
        documents = await db.scalar(text("SELECT count(*) FROM documents WHERE deleted_at IS NULL"))
    except Exception as exc:  # noqa: BLE001
        return Component("database", "Datenbank", "error", "nicht erreichbar", hint=str(exc)[:300])
    latency = (time.perf_counter() - started) * 1000
    ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    head = ScriptDirectory.from_config(Config(str(ini))).get_current_head() if ini.exists() else revision
    component = Component("database", "Datenbank", "ok", f"PostgreSQL {server.split(' ')[0]}", [
        ("Antwortzeit", f"{latency:.0f} ms"),
        ("Größe", _size(size or 0)),
        ("Dokumente (alle Haushalte)", str(documents)),
        ("Schema-Stand", revision or "-"),
    ])
    if head and revision != head:
        component.status = "warning"
        component.hint = f"Schema-Stand {revision}, erwartet {head} - HomeDMS neu starten, dann wird migriert."
    return component


async def check_worker(db: AsyncSession) -> Component:
    workers = (await db.execute(text(
        "SELECT count(*) FILTER (WHERE last_heartbeat > now() - make_interval(secs => :ok)), max(last_heartbeat) "
        "FROM procrastinate_workers"
    ), {"ok": HEARTBEAT_OK_SECONDS})).one()
    queues = (await db.execute(text(
        "SELECT queue_name, status::text, count(*) FROM procrastinate_jobs "
        "WHERE status IN ('todo', 'doing') GROUP BY queue_name, status"
    ))).all()
    failed = await db.scalar(text(
        "SELECT count(DISTINCT j.id) FROM procrastinate_jobs j JOIN procrastinate_events e ON e.job_id = j.id "
        "WHERE j.status = 'failed' AND e.type = 'failed' AND e.at > now() - interval '24 hours'"
    )) or 0
    stalled = await db.scalar(text(
        "SELECT count(*) FROM procrastinate_jobs j LEFT JOIN procrastinate_workers w ON w.id = j.worker_id "
        "WHERE j.status = 'doing' AND (w.id IS NULL OR w.last_heartbeat < now() - interval '60 seconds')"
    )) or 0
    oldest = await db.scalar(text(
        "SELECT min(e.at) FROM procrastinate_jobs j JOIN procrastinate_events e ON e.job_id = j.id "
        "WHERE j.status = 'todo' AND e.type = 'deferred' AND (j.scheduled_at IS NULL OR j.scheduled_at <= now())"
    ))
    counts: dict[str, dict[str, int]] = {}
    for queue, status, n in queues:
        counts.setdefault(queue, {})[status] = n
    waiting = sum(c.get("todo", 0) for c in counts.values())
    active, last_heartbeat = workers
    details = [
        ("Arbeitsstränge aktiv", f"{active} von 2"),
        ("Dateien (Texterkennung, Ablage)", _queue_text(counts.get("default", {}))),
        ("KI (Einordnung, Fristen)", _queue_text(counts.get("ai", {}))),
        ("Fehlgeschlagen (24 Std.)", str(failed)),
    ]
    if oldest:
        details.append(("Ältester wartender Auftrag", f"seit {_duration((datetime.now(timezone.utc) - oldest).total_seconds())}"))
    actions = [Action("restart-worker", "Worker neu starten",
                      "Laufende Aufträge werden abgebrochen; was dabei offen bleibt, holt „Prüfen > Nicht analysiert“ nach.")]
    if stalled:
        actions.insert(0, Action("retry-stalled", f"Hängende Aufträge neu starten ({stalled})"))
    if not active:
        hint = ("Docker: Container „app-worker“ prüfen (docker compose ps / logs app-worker)."
                if running_in_docker() else "Der Starter startet den Worker selbst neu - Protokoll worker.log prüfen.")
        if last_heartbeat:
            hint = f"Letztes Lebenszeichen vor {_duration((datetime.now(timezone.utc) - last_heartbeat).total_seconds())}. " + hint
        # Neustart per Auftrag geht nur, wenn der Worker laeuft
        return Component("worker", "Worker (Hintergrundverarbeitung)", "error", "läuft nicht", details, hint,
                         [a for a in actions if a.id == "retry-stalled"])
    status, summary = "ok", (f"{waiting} Aufträge warten" if waiting else "bereit")
    hint = None
    if stalled:
        status, hint = "warning", f"{stalled} Auftrag/Aufträge hängen (Worker zwischendurch abgebrochen)."
    elif failed:
        status, hint = "warning", "Fehlgeschlagene Aufträge: Details unten; betroffene Dokumente unter „Prüfen > Nicht analysiert“."
    return Component("worker", "Worker (Hintergrundverarbeitung)", status, summary, details, hint, actions)


def _queue_text(c: dict[str, int]) -> str:
    doing, todo = c.get("doing", 0), c.get("todo", 0)
    if not doing and not todo:
        return "leer"
    return ", ".join(p for p in (f"{doing} läuft" if doing else "", f"{todo} wartet" if todo else "") if p)


def _model_present(wanted: str, installed: set[str]) -> bool:
    name = wanted if ":" in wanted else f"{wanted}:latest"
    return name in installed or wanted in installed


async def check_ai(db: AsyncSession, tenant_id) -> Component:
    from homedms.ai import ollama
    from homedms.models.classification import AIModelConfig

    config = await db.scalar(select(AIModelConfig).where(AIModelConfig.tenant_id == tenant_id))
    client = ollama.client_for(config)
    try:
        async with client._client(4) as http:  # noqa: SLF001 - gleiche Verbindungseinstellungen wie die KI-Aufrufe
            version = (await http.get("/api/version")).json().get("version", "?")
            tags = (await http.get("/api/tags")).json().get("models", [])
            loaded = (await http.get("/api/ps")).json().get("models", [])
    except (httpx.HTTPError, ValueError) as exc:
        hint = ("Docker: Container „ollama“ prüfen." if running_in_docker()
                else "Ollama starten (Windows: läuft im angemeldeten Benutzer, Symbol im Infobereich).")
        return Component("ai", "KI (Ollama)", "error", "nicht erreichbar", [("Adresse", client.base_url)],
                         f"{hint} Dokumente ohne Analyse lassen sich danach unter „Prüfen > Nicht analysiert“ nachholen. ({str(exc)[:120]})")
    installed = {m.get("name", "") for m in tags}
    missing = [m for m in (client.chat_model, client.embedding_model) if not _model_present(m, installed)]
    details = [
        ("Version", version),
        ("Sprachmodell", client.chat_model + ("" if _model_present(client.chat_model, installed) else " – fehlt")),
        ("Embedding-Modell", client.embedding_model + ("" if _model_present(client.embedding_model, installed) else " – fehlt")),
        ("Im Arbeitsspeicher", ", ".join(m.get("name", "?") for m in loaded) or "nichts geladen"),
    ]
    actions = []
    if missing:
        actions.append(Action("pull-models", "Fehlende Modelle herunterladen", "Der Download (einige GB) läuft im Hintergrund."))
    if loaded:
        actions.append(Action("unload-models", "Arbeitsspeicher freigeben"))
    if missing:
        return Component("ai", "KI (Ollama)", "warning", f"Modell fehlt: {', '.join(missing)}", details,
                         "Ohne die Modelle bleiben Einordnung und Fristenerkennung aus.", actions)
    return Component("ai", "KI (Ollama)", "ok", "bereit" if not loaded else "bereit, Modell geladen", details, None, actions)


async def check_search(db: AsyncSession) -> Component:
    from homedms.core import meili

    settings = get_settings()
    if not settings.meilisearch_url:
        return Component("search", "Suche (Meilisearch)", "disabled", "nicht eingerichtet",
                         hint="Die Suche läuft über die Datenbank (Teilwörter, ohne Tippfehler-Toleranz).")
    client = meili.client()
    try:
        health = await client._request("GET", "/health", timeout=4)  # noqa: SLF001
        version = (await client._request("GET", "/version", timeout=4)).get("pkgVersion", "?")  # noqa: SLF001
        try:
            stats = await client._request("GET", f"/indexes/{meili.INDEX}/stats", timeout=4)  # noqa: SLF001
            indexed = stats.get("numberOfDocuments", 0)
        except meili.SearchUnavailable:
            indexed = 0
    except meili.SearchUnavailable as exc:
        return Component("search", "Suche (Meilisearch)", "error", "nicht erreichbar", [("Adresse", settings.meilisearch_url)],
                         f"Die Suche nutzt solange die Datenbank. ({str(exc)[:150]})",
                         [Action("reindex-search", "Suchindex neu aufbauen")])
    documents = await db.scalar(text("SELECT count(*) FROM documents WHERE deleted_at IS NULL")) or 0
    details = [("Version", version), ("Im Index", f"{indexed} von {documents} Dokumenten")]
    actions = [Action("reindex-search", "Suchindex neu aufbauen")]
    if health.get("status") != "available":
        return Component("search", "Suche (Meilisearch)", "warning", str(health.get("status")), details, None, actions)
    if indexed != documents:
        return Component("search", "Suche (Meilisearch)", "warning", "Index unvollständig", details,
                         "Nicht alle Dokumente sind im Suchindex - „Suchindex neu aufbauen“ behebt das.", actions)
    return Component("search", "Suche (Meilisearch)", "ok", "bereit", details, None, actions)


def _tesseract_info() -> tuple[str, list[str]]:
    import pytesseract

    from homedms.runtime import configure_tesseract

    configure_tesseract()
    return str(pytesseract.get_tesseract_version()), sorted(pytesseract.get_languages(config=""))


async def check_ocr() -> Component:
    wanted = [lang for lang in get_settings().ocr_languages.split("+") if lang]
    try:
        version, languages = await asyncio.wait_for(asyncio.to_thread(_tesseract_info), timeout=10)
    except Exception as exc:  # noqa: BLE001
        return Component("ocr", "Texterkennung (Tesseract)", "error", "nicht gefunden", [("Sprachen", "+".join(wanted))],
                         f"Tesseract installieren bzw. TESSERACT_CMD setzen. ({str(exc)[:150]})")
    missing = [lang for lang in wanted + ["osd"] if lang not in languages]
    details = [("Version", version.split()[0]), ("Sprachen", ", ".join(lang for lang in languages if lang != "osd"))]
    if missing:
        return Component("ocr", "Texterkennung (Tesseract)", "warning", f"Sprachpaket fehlt: {', '.join(missing)}", details,
                         "Ohne „osd“ werden quer fotografierte Seiten schlechter erkannt.")
    return Component("ocr", "Texterkennung (Tesseract)", "ok", "bereit", details)


def _storage_info(path: Path) -> tuple[int, int, bool]:
    path.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(path)
    try:
        with tempfile.NamedTemporaryFile(dir=path, prefix=".schreibtest-"):
            writable = True
    except OSError:
        writable = False
    return usage.free, usage.total, writable


async def check_storage() -> Component:
    settings = get_settings()
    try:
        free, total, writable = await asyncio.to_thread(_storage_info, Path(settings.documents_path))
        scan_ok = await asyncio.to_thread(lambda: Path(settings.scan_path).is_dir())
    except OSError as exc:
        return Component("storage", "Speicher", "error", "Ablage-Ordner nicht erreichbar", hint=str(exc)[:200])
    location = settings.scan_host_path or str(Path(settings.scan_path).resolve())
    details = [
        ("Frei", f"{_size(free)} von {_size(total)} ({free / total:.0%})".replace(".", ",") if total else "-"),
        ("Ablage", str(Path(settings.documents_path).resolve()) if not running_in_docker() else "Ordner DOCUMENTS_PATH"),
        ("Scan-Ordner", location + ("" if scan_ok else " – fehlt")),
    ]
    if not writable:
        return Component("storage", "Speicher", "error", "Ablage schreibgeschützt", details,
                         "HomeDMS kann keine Dateien speichern - Berechtigungen des Ordners prüfen.")
    if total and (free < 2 * 1024**3 or free / total < 0.05):
        return Component("storage", "Speicher", "warning", "wenig Platz", details, "Weniger als 2 GB bzw. 5 % frei.")
    return Component("storage", "Speicher", "ok", f"{_size(free)} frei", details)


async def check_tls() -> Component:
    from homedms.core import tls

    settings = get_settings()
    mode = settings.tls_mode.strip().lower()
    name = "Verschlüsselung (HTTPS)"
    if mode == "off":
        return Component("tls", name, "warning", "HomeDMS selbst verschlüsselt nicht", [("Modus", "hinter Reverse Proxy")],
                         "Nur in Ordnung, wenn ein Reverse Proxy (z. B. Synology) HTTPS macht und Port 8000 nicht "
                         "direkt aus dem Netz erreichbar ist.")
    if mode == "custom":
        return Component("tls", name, "ok", "eigenes Zertifikat", [("Zertifikat", settings.tls_cert_file)])
    info = tls.certificate_info(settings.tls_dir)
    if info is None:
        return Component("tls", name, "error", "kein Zertifikat",
                         hint="HomeDMS wurde nicht über den Starter (python -m homedms.server) gestartet.")
    days = (info["expires"] - datetime.now(timezone.utc)).days
    details = [
        ("Modus", "eigene Zertifizierungsstelle"),
        ("Abgedeckt", ", ".join(info["names"])),
        ("Gültig bis", f"{info['expires']:%d.%m.%Y} (erneuert sich selbst)"),
        ("Fingerabdruck", info["fingerprint"][:23] + "…"),
        ("Neues Gerät", f"http://<server>:{os.environ.get('PORT', '8000')}/zertifikat"),
    ]
    uncovered = sorted(tls.UNCOVERED)
    if uncovered:
        return Component("tls", name, "warning", "Adresse nicht abgedeckt", details,
                         f"Aufgerufen als {', '.join(uncovered)} - dafür warnt der Browser. In den Einstellungen "
                         "TLS_HOSTNAMES ergänzen und HomeDMS neu starten.")
    return Component("tls", name, "ok", f"aktiv, noch {days} Tage gültig", details)


async def check_notifications(db: AsyncSession, tenant_id) -> Component:
    """E-Mail-Versand und Push: eingerichtet? Letzter Versand geklappt?"""
    from homedms.core import mailer
    from homedms.models.ops import Notification, PushSubscription
    from homedms.models.tenant import Tenant, User

    name = "Erinnerungen (E-Mail/Push)"
    tenant = await db.get(Tenant, tenant_id)
    mail = tenant.mail_settings or {}
    devices = await db.scalar(
        select(func.count()).select_from(PushSubscription).join(User, User.id == PushSubscription.user_id)
        .where(User.tenant_id == tenant_id))
    week = datetime.now(timezone.utc) - timedelta(days=7)
    failed = (await db.execute(
        select(Notification.channel, func.count()).where(
            Notification.tenant_id == tenant_id, Notification.status == "failed", Notification.type == "digest",
            Notification.created_at > week).group_by(Notification.channel))).all()
    pending = await db.scalar(select(func.count()).where(
        Notification.tenant_id == tenant_id, Notification.status == "pending"))
    details = [
        ("E-Mail", f"über {mail.get('host')} als {mail.get('sender')}" if mailer.is_configured(mail) else "nicht eingerichtet"),
        ("Push-Geräte", str(devices or 0)),
        ("Zeitzone", get_settings().tz),
    ]
    if pending:
        details.append(("Warten auf Versand", str(pending)))
    for channel, count in failed:
        details.append((f"Fehlgeschlagen ({'E-Mail' if channel == 'email' else 'Push'}, 7 Tage)", str(count)))
    if mail.get("last_error"):
        return Component("notifications", name, "error", "E-Mail-Versand gestört", details,
                         f"{mail['last_error']} - unter „Benutzer“ > „E-Mail-Versand“ prüfen.")
    if failed:
        return Component("notifications", name, "warning", "Versand zuletzt fehlgeschlagen", details,
                         "Push braucht Internetzugang des Servers; Details stehen bei den Geräten unter „Konto & Sicherheit“.")
    if not mailer.is_configured(mail) and not devices:
        return Component("notifications", name, "disabled", "nur in der App (Glocke)", details,
                         "E-Mail unter „Benutzer“ > „E-Mail-Versand“ einrichten, Push unter „Konto & Sicherheit“ einschalten.")
    return Component("notifications", name, "ok", "eingerichtet", details)


async def recent_failures(db: AsyncSession, tenant_id, limit: int = 20) -> list[dict]:
    """Fehlgeschlagene Auftraege der letzten 7 Tage (eigene Dokumente bzw. ohne Dokumentbezug)."""
    rows = (await db.execute(text("""
        SELECT j.id, j.task_name, j.queue_name, max(e.at) AS at, j.args->>'document_id' AS document_id, d.title
        FROM procrastinate_jobs j
        JOIN procrastinate_events e ON e.job_id = j.id AND e.type = 'failed'
        LEFT JOIN documents d ON d.id::text = j.args->>'document_id'
        WHERE j.status = 'failed' AND e.at > now() - interval '7 days'
          AND (d.id IS NULL AND j.args->>'document_id' IS NULL OR d.tenant_id = :tenant)
        GROUP BY j.id, d.title
        ORDER BY at DESC
        LIMIT :limit
    """), {"tenant": tenant_id, "limit": limit})).all()
    return [
        {"job_id": r.id, "task": TASK_LABELS.get(r.task_name, r.task_name), "at": r.at,
         "document_id": r.document_id if r.title is not None else None, "document_title": r.title}
        for r in rows
    ]


async def _safe(coro, key: str, name: str) -> Component:
    try:
        return await asyncio.wait_for(coro, timeout=15)
    except Exception as exc:  # noqa: BLE001 - eine kaputte Pruefung darf die Seite nicht verhindern
        return Component(key, name, "error", "Prüfung fehlgeschlagen", hint=str(exc)[:200] or type(exc).__name__)


async def collect(tenant_id) -> list[Component]:
    """Alle Pruefungen parallel - jede mit eigener Datenbank-Sitzung."""
    from homedms.db import async_session_factory

    async def with_db(fn, *args):
        async with async_session_factory() as session:
            return await fn(session, *args)

    return list(await asyncio.gather(
        _safe(check_app(), "app", "HomeDMS"),
        _safe(with_db(check_database), "database", "Datenbank"),
        _safe(with_db(check_worker), "worker", "Worker (Hintergrundverarbeitung)"),
        _safe(with_db(check_ai, tenant_id), "ai", "KI (Ollama)"),
        _safe(with_db(check_search), "search", "Suche (Meilisearch)"),
        _safe(check_ocr(), "ocr", "Texterkennung (Tesseract)"),
        _safe(check_storage(), "storage", "Speicher"),
        _safe(check_tls(), "tls", "Verschlüsselung (HTTPS)"),
        _safe(with_db(check_notifications, tenant_id), "notifications", "Erinnerungen (E-Mail/Push)"),
    ))


