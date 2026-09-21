"""homedms/core/storage.py - reine Pfad-/Dateilogik, keine DB noetig."""
import uuid
from pathlib import Path

from homedms.core.storage import document_directory, document_file_path, save_upload


def test_document_directory_includes_tenant_and_year():
    tenant_id = uuid.uuid4()
    document_id = uuid.uuid4()
    path = document_directory(tenant_id, document_id)
    assert str(tenant_id) in path.parts
    assert str(document_id) in path.parts


def test_document_file_path_keeps_extension():
    tenant_id = uuid.uuid4()
    document_id = uuid.uuid4()
    path = document_file_path(tenant_id, document_id, page_number=1, original_filename="Rechnung.PDF")
    assert path.name.startswith("page-001")
    assert path.suffix.lower() == ".pdf"


def test_document_file_path_ignores_unsafe_original_name():
    tenant_id = uuid.uuid4()
    document_id = uuid.uuid4()
    # Pfad-Traversal-Versuch im Originalnamen darf sich nicht auswirken - nur die Endung zaehlt.
    path = document_file_path(tenant_id, document_id, page_number=2, original_filename="../../etc/passwd")
    assert path.name == "page-002"
    assert ".." not in path.parts


def test_save_upload_writes_file_and_returns_checksum(tmp_path):
    target = tmp_path / "sub" / "page-001.pdf"
    checksum = save_upload(target, b"hallo welt")
    assert target.read_bytes() == b"hallo welt"
    assert len(checksum) == 64  # sha256 hex
