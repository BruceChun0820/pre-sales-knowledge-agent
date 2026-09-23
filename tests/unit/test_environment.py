from importlib.metadata import version

import pydantic
import pydantic_settings
import pymupdf
from docx import Document
from qdrant_client import QdrantClient


def test_phase1_base_dependencies_are_importable() -> None:
    assert pydantic.__version__ == version("pydantic")
    assert pydantic_settings.__version__ == version("pydantic-settings")
    assert Document.__module__.startswith("docx")
    assert version("PyMuPDF") == pymupdf.__version__
    assert version("qdrant-client")


def test_pymupdf_smoke_extracts_text_from_generated_page() -> None:
    document = pymupdf.open()
    try:
        page = document.new_page()
        page.insert_text((72, 72), "phase-one smoke test")
        assert "phase-one smoke test" in page.get_text()
    finally:
        document.close()


def test_qdrant_memory_client_starts_with_empty_collections() -> None:
    client = QdrantClient(location=":memory:")
    try:
        assert client.get_collections().collections == []
    finally:
        client.close()
