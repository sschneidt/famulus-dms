"""Plattform-Details fuer den Betrieb ohne Docker (Windows-PC, Linux-Server) - an einer Stelle.

- Event-Loop: Procrastinate nutzt psycopg im async-Modus, und das laeuft unter Windows nur mit dem
  "Selector"-Loop (der Windows-Standard "Proactor" wird nicht unterstuetzt). Alle Einstiegspunkte
  (API, Worker, CLI, Migrationen) starten ihre Coroutine deshalb ueber run().
- Tesseract: unter Windows liegt tesseract.exe meist nicht im PATH -> Einstellung TESSERACT_CMD
  oder der Standard-Installationsort des UB-Mannheim-Installers.
"""
import asyncio
import os
import shutil
import sys
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

IS_WINDOWS = sys.platform == "win32"

WINDOWS_TESSERACT = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def run(coro: Coroutine[Any, Any, T]) -> T:
    """asyncio.run - unter Windows mit Selector-Loop (psycopg async)."""
    if IS_WINDOWS:
        with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
            return runner.run(coro)
    return asyncio.run(coro)


def find_tesseract(configured: str = "") -> str | None:
    """Pfad zu tesseract(.exe): Einstellung > PATH > Windows-Standardordner."""
    if configured:
        return configured
    found = shutil.which("tesseract")
    if found:
        return found
    if IS_WINDOWS:
        for candidate in WINDOWS_TESSERACT:
            if Path(candidate).is_file():
                return candidate
        local = os.environ.get("LOCALAPPDATA")
        if local and (Path(local) / "Programs" / "Tesseract-OCR" / "tesseract.exe").is_file():
            return str(Path(local) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
    return None


def configure_tesseract() -> str | None:
    import pytesseract

    from homedms.config import get_settings

    path = find_tesseract(get_settings().tesseract_cmd)
    if path:
        pytesseract.pytesseract.tesseract_cmd = path
    return path


def setup_logging(name: str) -> Path | None:
    """Protokoll auf die Konsole - und zusaetzlich in LOG_DIR/<name>.log, wenn LOG_DIR gesetzt ist
    (Windows-Autostart ohne Konsolenfenster, siehe scripts/install-windows.ps1). Die Dateien werden
    bei 5 MB gewechselt, die letzten 5 bleiben."""
    import logging
    from logging.handlers import RotatingFileHandler

    handlers: list[logging.Handler] = [logging.StreamHandler()]
    log_file = None
    log_dir = os.environ.get("LOG_DIR", "")
    if log_dir:
        Path(log_dir).mkdir(parents=True, exist_ok=True)
        log_file = Path(log_dir) / f"{name}.log"
        handlers.append(RotatingFileHandler(log_file, maxBytes=5_000_000, backupCount=5, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", handlers=handlers, force=True
    )
    return log_file


def bind_children_to_this_process() -> None:
    """Windows: Hilfsprozesse (Worker, Meilisearch) sollen mit dem Starter enden - auch wenn er hart
    beendet wird (Aufgabenplanung "Beenden", Absturz). Dafuer kommt der Starter in ein Job-Objekt
    mit "kill on close"; alle spaeter gestarteten Kindprozesse erben es. Unter Linux erledigt das
    systemd (alle Prozesse des Dienstes werden gemeinsam beendet)."""
    if not IS_WINDOWS:
        return
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):  # noqa: N801 - Windows-Namen
        _fields_ = [(n, ctypes.c_ulonglong) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class BASIC_LIMIT(ctypes.Structure):  # noqa: N801
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
        ]

    class EXTENDED_LIMIT(ctypes.Structure):  # noqa: N801
        _fields_ = [
            ("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return
    info = EXTENDED_LIMIT()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    kernel32.SetInformationJobObject(wintypes.HANDLE(job), 9, ctypes.byref(info), ctypes.sizeof(info))
    kernel32.AssignProcessToJobObject(wintypes.HANDLE(job), wintypes.HANDLE(kernel32.GetCurrentProcess()))
    # Der Handle bleibt bis zum Prozessende offen - absichtlich nie geschlossen
    globals()["_job_handle"] = job
