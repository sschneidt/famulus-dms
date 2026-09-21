"""homedms/models/document.py - reine Python-Objekte, keine DB noetig."""
import uuid

from homedms.models.document import DocumentFile


def test_document_file_filename_property_strips_path():
    doc_file = DocumentFile(
        id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        file_path="/data/documents/tenant-x/2026/doc-y/page-001.pdf",
        page_number=1,
        mime_type="application/pdf",
    )
    assert doc_file.filename == "page-001.pdf"
