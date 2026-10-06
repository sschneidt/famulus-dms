"""Sprachpakete der Texterkennung (Tesseract) - welche aktiv sind und Nachinstallieren.

Nutzerwunsch: Die Texterkennung richtet sich nach den Sprachen der Oberflaeche (wer Russisch
waehlt, bekommt russische Texterkennung), weitere Pakete lassen sich nachinstallieren.

- Aktiv fuer einen Haushalt: die vom Admin gewaehlten Sprachen (tenants.ocr_languages, sonst
  OCR_LANGUAGES aus der Konfiguration) plus die Oberflaechensprache jeder aktiven Person.
- Famulus DMS nutzt einen eigenen, beschreibbaren tessdata-Ordner (TESSDATA_DIR): Beim Start werden
  die mitgelieferten Pakete des Systems dorthin verlinkt/kopiert, nachinstallierte kommen dazu.
  Im Docker-Betrieb liegt er in einem eigenen Volume - Updates loeschen ihn nicht.
- Nachinstalliert wird aus tessdata_fast (offizielle Tesseract-Modelle, dieselben wie in den
  Debian-Paketen), im Hintergrund durch den Worker (tasks/system.py: install_ocr_language).
"""
import logging
import os
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from homedms.config import get_settings
from homedms.i18n import _
from homedms.models.ops import AppSetting
from homedms.models.tenant import Tenant, User

logger = logging.getLogger("homedms.ocr_languages")

# Angebotene Sprachen (Tesseract-Code -> Name in der Sprache selbst - so findet jede:r die eigene)
CATALOG: dict[str, str] = {
    "deu": "Deutsch", "eng": "English", "rus": "Русский", "ukr": "Українська", "bel": "Беларуская",
    "pol": "Polski", "ces": "Čeština", "slk": "Slovenčina", "hun": "Magyar", "ron": "Română",
    "bul": "Български", "hrv": "Hrvatski", "srp": "Српски", "slv": "Slovenščina", "bos": "Bosanski",
    "sqi": "Shqip", "ell": "Ελληνικά", "tur": "Türkçe", "fra": "Français", "ita": "Italiano",
    "spa": "Español", "por": "Português", "nld": "Nederlands", "dan": "Dansk", "swe": "Svenska",
    "nor": "Norsk", "fin": "Suomi", "lit": "Lietuvių", "lav": "Latviešu", "est": "Eesti",
    "kaz": "Қазақ тілі", "kat": "ქართული", "hye": "Հայերեն", "ara": "العربية", "fas": "فارسی",
    "heb": "עברית", "vie": "Tiếng Việt", "chi_sim": "中文（简体）", "jpn": "日本語", "kor": "한국어",
}
# Sprache der Oberflaeche -> Sprachpaket
UI_TO_OCR = {"de": "deu", "en": "eng", "ru": "rus"}
SYSTEM_DIRS = (  # wo Tesseract seine Pakete mitbringt (je nach System/Version)
    "/usr/share/tesseract-ocr/5/tessdata", "/usr/share/tesseract-ocr/4.00/tessdata", "/usr/share/tessdata",
    "/usr/local/share/tessdata", "/opt/homebrew/share/tessdata",
)
CODE = re.compile(r"^[a-z]{3}(_[a-z]{3,4})?$")
INSTALLS_KEY = "ocr_installs"
MIN_MODEL_BYTES = 100_000


class OcrLanguageError(Exception):
    pass


def tessdata_dir() -> Path:
    return Path(get_settings().tessdata_dir).resolve()


def system_dir() -> Path | None:
    """tessdata-Ordner der Tesseract-Installation (fuer die mitgelieferten Pakete)."""
    from homedms.runtime import find_tesseract

    candidates = []
    if os.environ.get("TESSDATA_PREFIX"):
        candidates.append(Path(os.environ["TESSDATA_PREFIX"]))
    exe = find_tesseract(get_settings().tesseract_cmd)
    if exe:
        try:  # neuere Versionen nennen den Ordner selbst
            out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=10).stdout
            match = re.search(r'in "([^"]+)"', out)
            if match:
                candidates.append(Path(match.group(1)))
        except (OSError, subprocess.SubprocessError):
            pass
        candidates.append(Path(exe).resolve().parent / "tessdata")  # Windows: neben tesseract.exe
    candidates += [Path(p) for p in SYSTEM_DIRS]
    own = tessdata_dir()
    for path in candidates:
        if path.is_dir() and path.resolve() != own and any(path.glob("*.traineddata")):
            return path
    return None


def prepare() -> Path:
    """Eigenen tessdata-Ordner anlegen und die mitgelieferten Pakete dorthin verlinken."""
    target = tessdata_dir()
    target.mkdir(parents=True, exist_ok=True)
    source = system_dir()
    if source is None:
        return target
    for model in source.glob("*.traineddata"):
        dest = target / model.name
        if dest.exists() or dest.is_symlink():
            if dest.is_symlink() and not dest.exists():  # Verweis ins Leere (System-Update) - neu setzen
                dest.unlink()
            else:
                continue
        try:
            dest.symlink_to(model)
        except OSError:  # Windows ohne Symlink-Recht
            shutil.copy2(model, dest)
    return target


def installed() -> set[str]:
    folder = tessdata_dir()
    if not folder.is_dir():
        return set()
    return {p.name.removesuffix(".traineddata") for p in folder.glob("*.traineddata") if p.exists()} - {"osd", "equ"}


def tesseract_config() -> str:
    """Zusatz fuer pytesseract (config=...): den eigenen tessdata-Ordner verwenden."""
    folder = tessdata_dir()
    return f'--tessdata-dir "{folder}"' if folder.is_dir() and any(folder.glob("*.traineddata")) else ""


def configured_default() -> list[str]:
    return [c for c in get_settings().ocr_languages.split("+") if c]


async def wanted(db: AsyncSession, tenant_id) -> list[str]:
    """Gewuenschte Sprachen eines Haushalts: Auswahl des Admins + Oberflaechensprachen der Personen."""
    tenant = await db.get(Tenant, tenant_id)
    chosen = list(tenant.ocr_languages) if tenant and tenant.ocr_languages else configured_default()
    locales = (await db.execute(
        select(User.locale).where(User.tenant_id == tenant_id, User.is_active.is_(True)).distinct()
    )).scalars().all()
    for locale in locales:
        code = UI_TO_OCR.get(locale or "")
        if code and code not in chosen:
            chosen.append(code)
    return chosen


async def lang_for(db: AsyncSession, tenant_id) -> str:
    """Sprachangabe fuer Tesseract ("deu+eng+rus") - nur installierte Pakete."""
    have = installed()
    codes = [c for c in await wanted(db, tenant_id) if c in have]
    if not codes:
        codes = [c for c in configured_default() if c in have] or sorted(have)[:1] or ["eng"]
    return "+".join(codes)


# --- Nachinstallieren ----------------------------------------------------------------------------

async def install_states(db: AsyncSession) -> dict:
    row = await db.get(AppSetting, INSTALLS_KEY)
    return dict(row.value) if row else {}


async def set_state(db: AsyncSession, code: str, state: dict | None) -> None:
    states = await install_states(db)
    if state is None:
        states.pop(code, None)
    else:
        states[code] = {**state, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    await db.execute(insert(AppSetting).values(key=INSTALLS_KEY, value=states)
                     .on_conflict_do_update(index_elements=["key"], set_={"value": states}))
    await db.commit()


def validate(code: str) -> None:
    if not CODE.match(code) or code not in CATALOG:
        raise OcrLanguageError(_("Unbekanntes Sprachpaket: {code}", code=code))


async def download(code: str, client: httpx.AsyncClient | None = None) -> Path:
    """Modell herunterladen und erst vollstaendig an seinen Platz legen (nie halbe Dateien)."""
    validate(code)
    url = get_settings().ocr_download_url.format(code=code)
    folder = prepare()
    own = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(30, read=120), follow_redirects=True)
    try:
        with tempfile.NamedTemporaryFile(dir=folder, prefix=f".{code}-", suffix=".part", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            try:
                async with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        raise OcrLanguageError(_("Download fehlgeschlagen ({status}) - {url}", status=response.status_code, url=url))
                    async for chunk in response.aiter_bytes():
                        tmp.write(chunk)
            except httpx.HTTPError as exc:
                raise OcrLanguageError(_("Download nicht möglich ({error}) - hat der Server Internetzugang?",
                                         error=exc.__class__.__name__)) from exc
        if tmp_path.stat().st_size < MIN_MODEL_BYTES:
            raise OcrLanguageError(_("Die heruntergeladene Datei ist kein Sprachpaket."))
        target = folder / f"{code}.traineddata"
        if target.is_symlink():
            target.unlink()
        os.replace(tmp_path, target)
        return target
    finally:
        if own:
            await client.aclose()
        for leftover in folder.glob(f".{code}-*.part"):
            leftover.unlink(missing_ok=True)


async def missing(db: AsyncSession, tenant_id) -> list[str]:
    have = installed()
    return [c for c in await wanted(db, tenant_id) if c not in have and c in CATALOG]


async def request_installs(db: AsyncSession, codes: list[str]) -> list[str]:
    """Download-Auftraege fuer fehlende Pakete einreihen (Worker). Rueckgabe: eingereihte Codes."""
    from procrastinate.exceptions import AlreadyEnqueued

    from homedms.jobs import app

    have = installed()
    queued = []
    async with app.open_async():
        for code in codes:
            if code in have or code not in CATALOG:
                continue
            try:
                await app.configure_task("install_ocr_language", queueing_lock=f"ocr-{code}").defer_async(code=code)
            except AlreadyEnqueued:
                pass
            await set_state(db, code, {"status": "installing"})
            queued.append(code)
    return queued
