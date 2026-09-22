from __future__ import annotations

import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.domain.models import (
    BlockType,
    Chunk,
    Confidentiality,
    DocumentRecord,
    DocumentType,
    EmbeddingBatch,
    IngestionError,
    IngestionErrorCode,
    IngestionResult,
    IngestionResultStatus,
    ParsedBlock,
    SourceLocation,
)

CHECKSUM = "a" * 64


def document_kwargs() -> dict[str, object]:
    return {
        "document_id": "doc-001",
        "document_version": "sha256-v1",
        "title": "Synthetic guide",
        "source_uri": "data/samples/guide.md",
        "document_type": DocumentType.PRODUCT_GUIDE,
        "confidentiality": Confidentiality.SYNTHETIC,
        "content_checksum": CHECKSUM,
    }


def chunk_kwargs() -> dict[str, object]:
    return {
        "document_id": "doc-001",
        "document_version": "sha256-v1",
        "chunk_id": "chunk-001",
        "text": "A source-preserving chunk.",
        "source_location": {"page_start": 1, "page_end": 1},
        "title": "Synthetic guide",
        "source_uri": "data/samples/guide.md",
        "document_type": DocumentType.PRODUCT_GUIDE,
        "confidentiality": Confidentiality.SYNTHETIC,
        "chunk_index": 0,
        "parser_version": "parser-v1",
        "cleaner_version": "cleaner-v1",
        "chunker_version": "chunker-v1",
        "content_checksum": CHECKSUM,
    }


def test_document_record_normalizes_labels_and_serializes() -> None:
    record = DocumentRecord(
        **document_kwargs(),
        industry=["finance", "finance"],
        products=[" Product X "],
    )

    assert record.tenant_id == "demo"
    assert record.active is False
    assert record.industry == ("finance",)
    assert record.products == ("Product X",)
    assert record.model_dump(mode="json")["document_type"] == "product_guide"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("document_id", " "),
        ("document_version", "version with spaces"),
        ("source_uri", " "),
        ("document_type", "not-a-document-type"),
    ],
)
def test_document_record_rejects_invalid_identity_and_type(field: str, value: object) -> None:
    payload = document_kwargs()
    payload[field] = value

    with pytest.raises(ValidationError):
        DocumentRecord(**payload)


def test_source_location_requires_stable_locator() -> None:
    with pytest.raises(ValidationError):
        SourceLocation()

    location = SourceLocation(section_path=["Overview"], char_start=0, char_end=12)
    assert location.section_path == ("Overview",)


def test_chunk_requires_pipeline_versions_and_source_location() -> None:
    with pytest.raises(ValidationError):
        Chunk(**{key: value for key, value in chunk_kwargs().items() if key != "cleaner_version"})

    with pytest.raises(ValidationError):
        Chunk(**{**chunk_kwargs(), "source_location": {}})


def test_parsed_block_and_embedding_batch_validate_order_and_dimensions() -> None:
    block = ParsedBlock(
        document_id="doc-001",
        document_version="sha256-v1",
        block_id="block-001",
        block_type=BlockType.PARAGRAPH,
        text="A paragraph.",
        source_location={"page_start": 1, "page_end": 1},
        order=0,
        parser_name="markdown",
        parser_version="parser-v1",
    )
    assert block.order == 0

    batch = EmbeddingBatch(
        model_name="test-model",
        model_revision="revision-1",
        dimension=2,
        chunk_ids=["chunk-001"],
        vectors=[[0.1, 0.2]],
    )
    assert batch.vectors == ((0.1, 0.2),)

    with pytest.raises(ValidationError):
        EmbeddingBatch(
            model_name="test-model",
            model_revision="revision-1",
            dimension=2,
            chunk_ids=["chunk-001"],
            vectors=[[0.1]],
        )


def test_ingestion_result_requires_error_for_failed_status() -> None:
    error = IngestionError(code=IngestionErrorCode.PARSE_FAILED, message="corrupt file")
    result = IngestionResult(
        document_id="doc-001",
        document_version="sha256-v1",
        status=IngestionResultStatus.FAILED,
        errors=[error],
    )
    assert result.errors[0].code == IngestionErrorCode.PARSE_FAILED

    with pytest.raises(ValidationError):
        IngestionResult(
            document_id="doc-001",
            document_version="sha256-v1",
            status=IngestionResultStatus.FAILED,
        )


def test_domain_import_does_not_load_external_adapter_sdks() -> None:
    code = (
        "import sys; from app.domain.models import Chunk; "
        "assert not any("
        "name in sys.modules for name in "
        "('qdrant_client', 'pymupdf', 'fitz', 'docx'))"
    )
    check = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert check.returncode == 0, check.stderr
