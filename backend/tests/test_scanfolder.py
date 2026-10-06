"""Hilfsfunktionen des Scan-Ordner-Imports (homedms/core/scanfolder.py)."""
import io
import os
import time
from pathlib import Path

import pytest
from PIL import Image

from homedms.core.scanfolder import (
    candidates,
    destination,
    is_ignored_name,
    is_settled,
    is_supported,
    looks_complete,
    migrate_legacy_dirs,
    title_from_filename,
)


def test_alte_ordner_werden_umbenannt(tmp_path: Path):
    (tmp_path / "_importiert/2026-09").mkdir(parents=True)
    (tmp_path / "_importiert/2026-09/alt.pdf").write_bytes(b"x")
    (tmp_path / "_fehler").mkdir()
    assert sorted(migrate_legacy_dirs(tmp_path)) == ["_fehler -> _failed", "_importiert -> _imported"]
    assert (tmp_path / "_imported/2026-09/alt.pdf").read_bytes() == b"x"  # Inhalt unveraendert
    assert (tmp_path / "_failed").is_dir()
    assert not (tmp_path / "_importiert").exists() and not (tmp_path / "_fehler").exists()
    assert migrate_legacy_dirs(tmp_path) == []  # zweiter Lauf: nichts mehr zu tun


def test_umbenennung_ueberschreibt_nie_einen_vorhandenen_neuen_ordner(tmp_path: Path):
    (tmp_path / "_importiert").mkdir()
    (tmp_path / "_importiert/alt.pdf").write_bytes(b"alt")
    (tmp_path / "_imported").mkdir()
    (tmp_path / "_imported/neu.pdf").write_bytes(b"neu")
    assert migrate_legacy_dirs(tmp_path) == []
    assert (tmp_path / "_importiert/alt.pdf").read_bytes() == b"alt"
    assert (tmp_path / "_imported/neu.pdf").read_bytes() == b"neu"


def test_ignorierte_namen():
    for name in (".DS_Store", "._Scan.pdf", "~$Brief.docx", "Thumbs.db", "scan.pdf.part", "x.tmp", ".hidden"):
        assert is_ignored_name(name), name
    assert not is_ignored_name("Scan_0815.pdf")


def test_candidates_ueberspringt_eigene_und_synology_ordner(tmp_path: Path):
    for rel in ("a.pdf", "sub/b.jpg", "_imported/2026-10/c.pdf", "_failed/d.pdf", "@eaDir/a.pdf/thumb.jpg",
                "_importiert/2026-09/alt.pdf", "_fehler/alt.pdf",  # alte deutsche Namen (bis 0.1.0)
                "#recycle/e.pdf", ".hidden/f.pdf", "sub/.DS_Store"):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    os.utime(tmp_path / "sub/b.jpg", (1, 1))  # aelteste zuerst
    assert [p.relative_to(tmp_path).as_posix() for p in candidates(tmp_path)] == ["sub/b.jpg", "a.pdf"]
    assert candidates(tmp_path / "gibtsnicht") == []


def test_candidates_folgt_keinen_verweisen(tmp_path: Path):
    outside = tmp_path / "aussen"
    outside.mkdir()
    (outside / "geheim.pdf").write_bytes(b"x")
    scan = tmp_path / "scan"
    scan.mkdir()
    try:
        (scan / "link").symlink_to(outside)
        (scan / "link.pdf").symlink_to(outside / "geheim.pdf")
    except OSError:  # Windows: Symlinks brauchen Entwicklermodus oder Administratorrechte
        pytest.skip("Symlinks sind auf diesem Rechner nicht erlaubt (Windows: Entwicklermodus einschalten)")
    assert candidates(scan) == []


def test_unterstuetzte_typen():
    assert is_supported(Path("a.PDF")) and is_supported(Path("b.heic")) and is_supported(Path("c.eml"))
    assert not is_supported(Path("d.docx")) and not is_supported(Path("e"))


def test_is_settled(tmp_path: Path):
    p = tmp_path / "a.pdf"
    p.write_bytes(b"x")
    assert not is_settled(p)
    assert is_settled(p, now=time.time() + 31)
    assert not is_settled(tmp_path / "weg.pdf")


def _png(truncate: int = 0) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, format="PNG")
    data = buf.getvalue()
    return data[:-truncate] if truncate else data


def test_looks_complete():
    assert looks_complete(Path("a.pdf"), b"%PDF-1.7\n...\n%%EOF\n") is None
    assert "unvollstaendig" in looks_complete(Path("a.pdf"), b"%PDF-1.7\n... abgebrochen")
    assert "keine gueltige" in looks_complete(Path("a.pdf"), b"<html>")
    assert looks_complete(Path("a.png"), _png()) is None
    assert "nicht lesbar" in looks_complete(Path("a.png"), _png(truncate=30))
    assert looks_complete(Path("a.pdf"), b"") == "Datei ist leer"


def test_destination_und_titel(tmp_path: Path):
    assert destination(tmp_path, "Scan.pdf") == tmp_path / "Scan.pdf"
    (tmp_path / "Scan.pdf").write_bytes(b"x")
    (tmp_path / "Scan (2).pdf").write_bytes(b"x")
    assert destination(tmp_path, "Scan.pdf") == tmp_path / "Scan (3).pdf"
    assert title_from_filename("Scan_2026-10-02_0815.pdf") == "Scan_2026-10-02_0815"


def test_scan_ordner_info_zeigt_echten_ordner(monkeypatch, tmp_path):
    """Seite "Scan-Ordner": Docker -> Pfad aus der .env; ohne Docker -> SCAN_PATH selbst."""
    import asyncio

    from homedms.api.routes.import_sources import scan_folder_info
    from homedms.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "scan_host_path", "/volume1/scan")
    info = asyncio.run(scan_folder_info(user=None))
    assert info.docker and info.location == "/volume1/scan" and info.setting == "SCAN_FOLDER_PATH"

    monkeypatch.setattr(settings, "scan_host_path", "")
    monkeypatch.setattr(settings, "scan_path", str(tmp_path))
    info = asyncio.run(scan_folder_info(user=None))
    assert not info.docker and info.location == str(tmp_path.resolve()) and info.setting == "SCAN_PATH"
