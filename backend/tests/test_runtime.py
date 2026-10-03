"""Betrieb ohne Docker: Starter (homedms/server.py) und Plattform-Helfer (homedms/runtime.py)."""
import logging
import sys
import time

from homedms import runtime, server


def test_run_liefert_ergebnis_der_coroutine():
    async def antwort():
        return 42

    assert runtime.run(antwort()) == 42


def test_tesseract_suche(monkeypatch, tmp_path):
    assert runtime.find_tesseract("C:/Tools/tesseract.exe") == "C:/Tools/tesseract.exe"  # Einstellung zuerst
    monkeypatch.setattr(runtime.shutil, "which", lambda name: "/usr/bin/tesseract")
    assert runtime.find_tesseract("") == "/usr/bin/tesseract"
    # Windows: nicht im PATH -> Standardordner des Installers
    exe = tmp_path / "Tesseract-OCR" / "tesseract.exe"
    exe.parent.mkdir()
    exe.write_bytes(b"")
    monkeypatch.setattr(runtime.shutil, "which", lambda name: None)
    monkeypatch.setattr(runtime, "IS_WINDOWS", True)
    monkeypatch.setattr(runtime, "WINDOWS_TESSERACT", ("C:/gibt/es/nicht.exe", str(exe)))
    assert runtime.find_tesseract("") == str(exe)
    monkeypatch.setattr(runtime, "IS_WINDOWS", False)
    assert runtime.find_tesseract("") is None


def test_protokoll_datei_mit_log_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    path = runtime.setup_logging("homedms")
    logging.getLogger("homedms.test").info("Hallo Protokoll")
    for handler in logging.getLogger().handlers:
        handler.flush()
    assert path == tmp_path / "logs" / "homedms.log"
    assert "Hallo Protokoll" in path.read_text(encoding="utf-8")
    monkeypatch.delenv("LOG_DIR")
    assert runtime.setup_logging("homedms") is None


def test_einstellungsdatei_vorhandene_variablen_haben_vorrang(monkeypatch, tmp_path):
    env = tmp_path / "homedms.env"
    env.write_text("HOMEDMS_TEST_A=aus-datei\nHOMEDMS_TEST_B=aus-datei\nSCAN_PATH=C:/HomeDMS-Daten/scan\n", encoding="utf-8")
    monkeypatch.setenv("HOMEDMS_ENV", str(env))
    monkeypatch.setenv("HOMEDMS_TEST_B", "gesetzt")
    monkeypatch.delenv("HOMEDMS_TEST_A", raising=False)
    monkeypatch.delenv("SCAN_PATH", raising=False)
    assert server.load_env_file() == env
    import os

    assert os.environ["HOMEDMS_TEST_A"] == "aus-datei"
    assert os.environ["HOMEDMS_TEST_B"] == "gesetzt"
    assert os.environ["SCAN_PATH"] == "C:/HomeDMS-Daten/scan"
    for key in ("HOMEDMS_TEST_A", "SCAN_PATH"):
        monkeypatch.delenv(key)
    monkeypatch.setenv("HOMEDMS_ENV", str(tmp_path / "fehlt.env"))
    assert server.load_env_file() is None


def test_abgestuerzter_hilfsprozess_wird_neu_gestartet(tmp_path):
    marker = tmp_path / "starts.txt"
    script = f"open({str(marker)!r}, 'a').write('x'); raise SystemExit(3)"
    child = server.Child("Test", [sys.executable, "-c", script], cwd=tmp_path)
    child.start()
    deadline = time.time() + 15
    while time.time() < deadline and len(marker.read_text() if marker.exists() else "") < 2:
        time.sleep(0.2)
    child.stop()
    assert len(marker.read_text()) >= 2  # erster Start + mindestens ein Neustart


def test_worker_neustart_beendet_die_arbeitsstraenge():
    import asyncio

    from homedms import worker

    async def main():
        stopped = asyncio.Event()
        worker._stop = lambda *_: stopped.set()
        try:
            assert worker.request_restart() is True
            await asyncio.wait_for(stopped.wait(), timeout=3)
        finally:
            worker._stop = None
        assert worker.request_restart() is False  # ausserhalb des Workers: nichts zu tun

    runtime.run(main())
