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

from homedms import i18n
from homedms.config import get_settings
from homedms.i18n import N_, _, _n

STARTED_AT = time.time()
HEARTBEAT_OK_SECONDS = 60
TASK_LABELS = {
    "ocr_document": N_("Texterkennung"),
    "classify_document": N_("Einordnung"),
    "extract_metadata": N_("Betreff/Fristen"),
    "file_document": N_("Ablage"),
    "scan_folders": N_("Scan-Ordner"),
    "learn_exemplar": N_("Lernen"),
    "pull_model": N_("KI-Modell laden"),
    "restart_worker": N_("Worker-Neustart"),
    "ping": N_("Test"),
    "send_reminders": N_("Erinnerungen"),
    "install_ocr_language": N_("Sprachpaket laden"),
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
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else _("{value} {unit}", value=_decimal(n), unit=unit)
        n /= 1024
    return str(n)


def _decimal(value: float) -> str:
    """Eine Nachkommastelle mit dem Dezimalzeichen der Sprache."""
    text = f"{value:.1f}"
    return text if i18n.current() == "en" else text.replace(".", ",")


def _duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 90:
        return _("{count} s", count=seconds)
    if seconds < 5400:
        return _("{count} Min.", count=seconds // 60)
    if seconds < 172800:
        return _("{count} Std.", count=seconds // 3600)
    return _n("{count} Tag", "{count} Tage", seconds // 86400)


def running_in_docker() -> bool:
    return Path("/.dockerenv").exists() or bool(get_settings().scan_host_path)


# --- einzelne Pruefungen ---------------------------------------------------------------------


async def check_app() -> Component:
    from homedms import __version__ as app_version  # einzige Quelle; im Docker-Image ist das Projekt nicht als Paket installiert

    mode ="Docker" if running_in_docker() else _("ohne Docker ({system})", system=platform.system())
    return Component("app", "Famulus DMS", "ok", _("läuft seit {duration}", duration=_duration(time.time() - STARTED_AT)), [
        (_("Version"), app_version),
        (_("Betrieb"), mode),
        ("Python", platform.python_version()),
        (_("Rechner"), platform.node() or "-"),
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
        return Component("database", _("Datenbank"), "error", _("nicht erreichbar"), hint=str(exc)[:300])
    latency = (time.perf_counter() - started) * 1000
    ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    head = ScriptDirectory.from_config(Config(str(ini))).get_current_head() if ini.exists() else revision
    component = Component("database", _("Datenbank"), "ok", f"PostgreSQL {server.split(' ')[0]}", [
        (_("Antwortzeit"), f"{latency:.0f} ms"),
        (_("Größe"), _size(size or 0)),
        (_("Dokumente (alle Haushalte)"), str(documents)),
        (_("Schema-Stand"), revision or "-"),
    ])
    if head and revision != head:
        component.status = "warning"
        component.hint = _("Schema-Stand {revision}, erwartet {head} - Famulus DMS neu starten, dann wird migriert.",
                           revision=revision, head=head)
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
        (_("Arbeitsstränge aktiv"), _("{active} von {total}", active=active, total=2)),
        (_("Dateien (Texterkennung, Ablage)"), _queue_text(counts.get("default", {}))),
        (_("KI (Einordnung, Fristen)"), _queue_text(counts.get("ai", {}))),
        (_("Fehlgeschlagen (24 Std.)"), str(failed)),
    ]
    if oldest:
        details.append((_("Ältester wartender Auftrag"),
                        _("seit {duration}", duration=_duration((datetime.now(timezone.utc) - oldest).total_seconds()))))
    actions = [Action("restart-worker", _("Worker neu starten"),
                      _("Laufende Aufträge werden abgebrochen; was dabei offen bleibt, holt „Prüfen > Nicht analysiert“ nach."))]
    if stalled:
        actions.insert(0, Action("retry-stalled", _("Hängende Aufträge neu starten ({count})", count=stalled)))
    name = _("Worker (Hintergrundverarbeitung)")
    if not active:
        hint = (_("Docker: Container „app-worker“ prüfen (docker compose ps / logs app-worker).")
                if running_in_docker() else _("Der Starter startet den Worker selbst neu - Protokoll worker.log prüfen."))
        if last_heartbeat:
            since = _duration((datetime.now(timezone.utc) - last_heartbeat).total_seconds())
            hint = _("Letztes Lebenszeichen vor {duration}.", duration=since) + " " + hint
        # Neustart per Auftrag geht nur, wenn der Worker laeuft
        return Component("worker", name, "error", _("läuft nicht"), details, hint,
                         [a for a in actions if a.id == "retry-stalled"])
    status, summary = "ok", (_n("{count} Auftrag wartet", "{count} Aufträge warten", waiting) if waiting else _("bereit"))
    hint = None
    if stalled:
        status, hint = "warning", _n("{count} Auftrag hängt (Worker zwischendurch abgebrochen).",
                                     "{count} Aufträge hängen (Worker zwischendurch abgebrochen).", stalled)
    elif failed:
        status, hint = "warning", _("Fehlgeschlagene Aufträge: Details unten; betroffene Dokumente unter „Prüfen > Nicht analysiert“.")
    return Component("worker", name, status, summary, details, hint, actions)


def _queue_text(c: dict[str, int]) -> str:
    doing, todo = c.get("doing", 0), c.get("todo", 0)
    if not doing and not todo:
        return _("leer")
    return ", ".join(p for p in (_("{count} läuft", count=doing) if doing else "",
                                 _("{count} wartet", count=todo) if todo else "") if p)


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
        hint = (_("Docker: Container „ollama“ prüfen.") if running_in_docker()
                else _("Ollama starten (Windows: läuft im angemeldeten Benutzer, Symbol im Infobereich)."))
        later = _("Dokumente ohne Analyse lassen sich danach unter „Prüfen > Nicht analysiert“ nachholen.")
        return Component("ai", _("KI (Ollama)"), "error", _("nicht erreichbar"), [(_("Adresse"), client.base_url)],
                         f"{hint} {later} ({str(exc)[:120]})")
    installed = {m.get("name", "") for m in tags}
    missing = [m for m in (client.chat_model, client.embedding_model) if not _model_present(m, installed)]
    details = [
        (_("Version"), version),
        (_("Sprachmodell"), client.chat_model + ("" if _model_present(client.chat_model, installed) else " – " + _("fehlt"))),
        (_("Embedding-Modell"),
         client.embedding_model + ("" if _model_present(client.embedding_model, installed) else " – " + _("fehlt"))),
        (_("Im Arbeitsspeicher"), ", ".join(m.get("name", "?") for m in loaded) or _("nichts geladen")),
    ]
    actions = []
    if missing:
        actions.append(Action("pull-models", _("Fehlende Modelle herunterladen"), _("Der Download (einige GB) läuft im Hintergrund.")))
    if loaded:
        actions.append(Action("unload-models", _("Arbeitsspeicher freigeben")))
    if missing:
        return Component("ai", _("KI (Ollama)"), "warning", _("Modell fehlt: {models}", models=", ".join(missing)), details,
                         _("Ohne die Modelle bleiben Einordnung und Fristenerkennung aus."), actions)
    return Component("ai", _("KI (Ollama)"), "ok", _("bereit") if not loaded else _("bereit, Modell geladen"), details, None, actions)


async def check_search(db: AsyncSession) -> Component:
    from homedms.core import meili

    settings = get_settings()
    if not settings.meilisearch_url:
        return Component("search", _("Suche (Meilisearch)"), "disabled", _("nicht eingerichtet"),
                         hint=_("Die Suche läuft über die Datenbank (Teilwörter, ohne Tippfehler-Toleranz)."))
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
        return Component("search", _("Suche (Meilisearch)"), "error", _("nicht erreichbar"),
                         [(_("Adresse"), settings.meilisearch_url)],
                         _("Die Suche nutzt solange die Datenbank.") + f" ({str(exc)[:150]})",
                         [Action("reindex-search", _("Suchindex neu aufbauen"))])
    documents = await db.scalar(text("SELECT count(*) FROM documents WHERE deleted_at IS NULL")) or 0
    details = [(_("Version"), version), (_("Im Index"), _("{indexed} von {total} Dokumenten", indexed=indexed, total=documents))]
    actions = [Action("reindex-search", _("Suchindex neu aufbauen"))]
    name = _("Suche (Meilisearch)")
    if health.get("status") != "available":
        return Component("search", name, "warning", str(health.get("status")), details, None, actions)
    if indexed != documents:
        return Component("search", name, "warning", _("Index unvollständig"), details,
                         _("Nicht alle Dokumente sind im Suchindex - „Suchindex neu aufbauen“ behebt das."), actions)
    return Component("search", name, "ok", _("bereit"), details, None, actions)


def _tesseract_info() -> tuple[str, list[str]]:
    import pytesseract

    from homedms.core import ocr_languages
    from homedms.runtime import configure_tesseract

    configure_tesseract()
    config = ocr_languages.tesseract_config()
    return str(pytesseract.get_tesseract_version()), sorted(pytesseract.get_languages(config=config))


async def check_ocr(db: AsyncSession, tenant_id) -> Component:
    from homedms.core import ocr_languages

    name = _("Texterkennung (Tesseract)")
    wanted = await ocr_languages.wanted(db, tenant_id)
    try:
        version, languages = await asyncio.wait_for(asyncio.to_thread(_tesseract_info), timeout=10)
    except Exception as exc:  # noqa: BLE001
        return Component("ocr", name, "error", _("nicht gefunden"), [(_("Sprachen"), "+".join(wanted))],
                         _("Tesseract installieren bzw. TESSERACT_CMD setzen.") + f" ({str(exc)[:150]})")
    missing = [lang for lang in wanted if lang not in languages]
    states = await ocr_languages.install_states(db)
    details = [
        (_("Version"), version.split()[0]),
        (_("Verwendet"), await ocr_languages.lang_for(db, tenant_id)),
        (_("Installiert"), ", ".join(lang for lang in languages if lang != "osd")),
    ]
    if missing:
        failed = [states[c]["error"] for c in missing if (states.get(c) or {}).get("status") == "failed"]
        installing = [c for c in missing if (states.get(c) or {}).get("status") == "installing"]
        hint = (failed[0] if failed else _("Wird gerade heruntergeladen.") if installing
                else _("Fehlende Pakete lassen sich unter „Sprachen“ oder hier nachladen."))
        return Component("ocr", name, "warning", _("Sprachpaket fehlt: {codes}", codes=", ".join(missing)), details,
                         hint, [Action("install-ocr-languages", _("Sprachpakete herunterladen"))])
    if "osd" not in languages:
        return Component("ocr", name, "warning", _("Sprachpaket fehlt: {codes}", codes="osd"), details,
                         _("Ohne „osd“ werden quer fotografierte Seiten schlechter erkannt."))
    return Component("ocr", name, "ok", _("bereit"), details)


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
        return Component("storage", _("Speicher"), "error", _("Ablage-Ordner nicht erreichbar"), hint=str(exc)[:200])
    location = settings.scan_host_path or str(Path(settings.scan_path).resolve())
    details = [
        (_("Frei"), _("{free} von {total} ({percent} %)", free=_size(free), total=_size(total),
                      percent=round(free / total * 100)) if total else "-"),
        (_("Ablage"), str(Path(settings.documents_path).resolve()) if not running_in_docker() else _("Ordner DOCUMENTS_PATH")),
        (_("Scan-Ordner"), location + ("" if scan_ok else " – " + _("fehlt"))),
    ]
    name = _("Speicher")
    if not writable:
        return Component("storage", name, "error", _("Ablage schreibgeschützt"), details,
                         _("Famulus DMS kann keine Dateien speichern - Berechtigungen des Ordners prüfen."))
    if total and (free < 2 * 1024**3 or free / total < 0.05):
        return Component("storage", name, "warning", _("wenig Platz"), details, _("Weniger als 2 GB bzw. 5 % frei."))
    return Component("storage", name, "ok", _("{size} frei", size=_size(free)), details)


async def check_tls() -> Component:
    from homedms.core import tls

    settings = get_settings()
    mode = settings.tls_mode.strip().lower()
    name = _("Verschlüsselung (HTTPS)")
    if mode == "off":
        return Component("tls", name, "warning", _("Famulus DMS selbst verschlüsselt nicht"),
                         [(_("Modus"), _("hinter Reverse Proxy"))],
                         _("Nur in Ordnung, wenn ein Reverse Proxy (z. B. Synology) HTTPS macht und Port 8000 nicht "
                           "direkt aus dem Netz erreichbar ist."))
    if mode == "custom":
        return Component("tls", name, "ok", _("eigenes Zertifikat"), [(_("Zertifikat"), settings.tls_cert_file)])
    info = tls.certificate_info(settings.tls_dir)
    if info is None:
        return Component("tls", name, "error", _("kein Zertifikat"),
                         hint=_("Famulus DMS wurde nicht über den Starter (python -m homedms.server) gestartet."))
    days = (info["expires"] - datetime.now(timezone.utc)).days
    details = [
        (_("Modus"), _("eigene Zertifizierungsstelle")),
        (_("Abgedeckt"), ", ".join(info["names"])),
        (_("Gültig bis"), _("{date} (erneuert sich selbst)", date=i18n.format_date(info["expires"]))),
        (_("Fingerabdruck"), info["fingerprint"][:23] + "…"),
        (_("Neues Gerät"), f"http://<server>:{os.environ.get('PORT', '8000')}/zertifikat"),
    ]
    uncovered = sorted(tls.UNCOVERED)
    if uncovered:
        return Component("tls", name, "warning", _("Adresse nicht abgedeckt"), details,
                         _("Aufgerufen als {hosts} - dafür warnt der Browser. In den Einstellungen "
                           "TLS_HOSTNAMES ergänzen und Famulus DMS neu starten.", hosts=", ".join(uncovered)))
    return Component("tls", name, "ok", _n("aktiv, noch {count} Tag gültig", "aktiv, noch {count} Tage gültig", days), details)


async def check_notifications(db: AsyncSession, tenant_id) -> Component:
    """E-Mail-Versand und Push: eingerichtet? Letzter Versand geklappt?"""
    from homedms.core import mailer
    from homedms.models.ops import Notification, PushSubscription
    from homedms.models.tenant import Tenant, User

    name = _("Erinnerungen (E-Mail/Push)")
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
        (_("E-Mail"), _("über {host} als {sender}", host=mail.get("host"), sender=mail.get("sender"))
         if mailer.is_configured(mail) else _("nicht eingerichtet")),
        (_("Push-Geräte"), str(devices or 0)),
        (_("Zeitzone"), get_settings().tz),
    ]
    if pending:
        details.append((_("Warten auf Versand"), str(pending)))
    for channel, count in failed:
        details.append((_("Fehlgeschlagen ({channel}, 7 Tage)", channel=_("E-Mail") if channel == "email" else "Push"),
                        str(count)))
    if mail.get("last_error"):
        return Component("notifications", name, "error", _("E-Mail-Versand gestört"), details,
                         _("{error} - unter „Benutzer“ > „E-Mail-Versand“ prüfen.", error=mail["last_error"]))
    if failed:
        return Component("notifications", name, "warning", _("Versand zuletzt fehlgeschlagen"), details,
                         _("Push braucht Internetzugang des Servers; Details stehen bei den Geräten unter „Konto & Sicherheit“."))
    if not mailer.is_configured(mail) and not devices:
        return Component("notifications", name, "disabled", _("nur in der App (Glocke)"), details,
                         _("E-Mail unter „Benutzer“ > „E-Mail-Versand“ einrichten, Push unter „Konto & Sicherheit“ einschalten."))
    return Component("notifications", name, "ok", _("eingerichtet"), details)


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
        {"job_id": r.id, "task": _(TASK_LABELS[r.task_name]) if r.task_name in TASK_LABELS else r.task_name, "at": r.at,
         "document_id": r.document_id if r.title is not None else None, "document_title": r.title}
        for r in rows
    ]


async def _safe(coro, key: str, name: str) -> Component:
    try:
        return await asyncio.wait_for(coro, timeout=15)
    except Exception as exc:  # noqa: BLE001 - eine kaputte Pruefung darf die Seite nicht verhindern
        return Component(key, name, "error", _("Prüfung fehlgeschlagen"), hint=str(exc)[:200] or type(exc).__name__)


async def collect(tenant_id) -> list[Component]:
    """Alle Pruefungen parallel - jede mit eigener Datenbank-Sitzung."""
    from homedms.db import async_session_factory

    async def with_db(fn, *args):
        async with async_session_factory() as session:
            return await fn(session, *args)

    return list(await asyncio.gather(
        _safe(check_app(), "app", "Famulus DMS"),
        _safe(with_db(check_database), "database", _("Datenbank")),
        _safe(with_db(check_worker), "worker", _("Worker (Hintergrundverarbeitung)")),
        _safe(with_db(check_ai, tenant_id), "ai", _("KI (Ollama)")),
        _safe(with_db(check_search), "search", _("Suche (Meilisearch)")),
        _safe(with_db(check_ocr, tenant_id), "ocr", _("Texterkennung (Tesseract)")),
        _safe(check_storage(), "storage", _("Speicher")),
        _safe(check_tls(), "tls", _("Verschlüsselung (HTTPS)")),
        _safe(with_db(check_notifications, tenant_id), "notifications", _("Erinnerungen (E-Mail/Push)")),
    ))


