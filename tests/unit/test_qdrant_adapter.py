from __future__ import annotations

import hashlib

import pytest
from qdrant_client import QdrantClient

from app.domain.models import (
    Chunk,
    Confidentiality,
    DocumentType,
    EmbeddingBatch,
    Language,
    SourceLocation,
)
from app.rag.vector_store import (
    EmbeddingModelMismatchError,
    QdrantVectorStore,
    VectorDimensionMismatchError,
    VectorStoreError,
)


def _chunk(
    chunk_id: str,
    *,
    version: str = "v1",
    active: bool = False,
    industry: tuple[str, ...] = ("finance",),
    products: tuple[str, ...] = ("agent-x",),
) -> Chunk:
    text = f"Evidence for {chunk_id}"
    checksum = hashlib.sha256(text.encode()).hexdigest()
    source_checksum = hashlib.sha256(b"source").hexdigest()
    return Chunk(
        document_id="doc-one",
        document_version=version,
        chunk_id=chunk_id,
        text=text,
        text_checksum=checksum,
        source_location=SourceLocation(page_start=1, page_end=1),
        title="Synthetic document",
        source_uri="samples/guide.txt",
        document_type=DocumentType.PRODUCT_GUIDE,
        industry=industry,
        products=products,
        language=Language.EN,
        active=active,
        confidentiality=Confidentiality.SYNTHETIC,
        section_path=("Overview",),
        chunk_index=0,
        parser_version="parser-v1",
        cleaner_version="cleaner-v1",
        chunker_version="chunker-v1",
        content_checksum=source_checksum,
    )


def _batch(chunks: tuple[Chunk, ...], *, model: str = "model-a", dimension: int = 3):
    return EmbeddingBatch(
        model_name=model,
        model_revision="revision-a",
        dimension=dimension,
        chunk_ids=tuple(chunk.chunk_id for chunk in chunks),
        vectors=tuple((1.0, 0.0, 0.0)[:dimension] for _ in chunks),
        normalized=True,
    )


def _store(client: QdrantClient | None = None, *, name: str = "unit"):
    return QdrantVectorStore(
        client or QdrantClient(":memory:"),
        collection_name=name,
        model_name="model-a",
        model_revision="revision-a",
        dimension=3,
    )


def test_qdrant_adapter_upsert_is_idempotent_and_returns_domain_chunks() -> None:
    store = _store()
    chunk = _chunk("stable-chunk", active=True)
    store.upsert((chunk,), _batch((chunk,)))
    point_id = store.point_id(chunk.chunk_id)
    store.upsert((chunk,), _batch((chunk,)))

    assert point_id == store.point_id(chunk.chunk_id)
    assert store.count(tenant_id="demo") == 1
    found = store.search((1.0, 0.0, 0.0), tenant_id="demo", limit=5)
    assert len(found) == 1
    assert isinstance(found[0], Chunk)
    assert found[0].chunk_id == chunk.chunk_id


def test_qdrant_adapter_applies_active_and_metadata_filters() -> None:
    store = _store()
    matching = _chunk("matching", active=True)
    inactive = _chunk("inactive", active=False)
    other = _chunk(
        "other",
        active=True,
        industry=("healthcare",),
        products=("agent-y",),
    )
    for chunk in (matching, inactive, other):
        store.upsert((chunk,), _batch((chunk,)))

    results = store.search(
        (1.0, 0.0, 0.0),
        tenant_id="demo",
        limit=10,
        filters={"industry": "finance", "document_type": "product_guide", "products": "agent-x"},
    )
    assert [chunk.chunk_id for chunk in results] == ["matching"]
    assert store.count(tenant_id="demo", filters={"active": False}, active_only=False) == 1
    with pytest.raises(ValueError, match="unsupported"):
        store.search((1.0, 0.0, 0.0), tenant_id="demo", limit=2, filters={"secret": "x"})


def test_qdrant_adapter_rejects_dimension_and_model_mismatch() -> None:
    store = _store()
    chunk = _chunk("chunk-a")
    with pytest.raises(VectorDimensionMismatchError):
        store.upsert((chunk,), _batch((chunk,), dimension=2))
    with pytest.raises(EmbeddingModelMismatchError):
        store.upsert((chunk,), _batch((chunk,), model="other-model"))
    with pytest.raises(VectorDimensionMismatchError):
        store.search((1.0, 0.0), tenant_id="demo", limit=1)
    with pytest.raises(ValueError, match="unique"):
        store.upsert(
            (chunk, chunk),
            EmbeddingBatch(
                model_name="model-a",
                model_revision="revision-a",
                dimension=3,
                chunk_ids=(chunk.chunk_id, chunk.chunk_id),
                vectors=((1.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
            ),
        )


def test_qdrant_adapter_activates_only_present_versions() -> None:

    store = _store()
    old = _chunk("old-point", version="v1", active=True)
    new = _chunk("new-point", version="v2")
    store.upsert((old,), _batch((old,)))
    with pytest.raises(VectorStoreError, match="missing version"):
        store.activate_version(document_id="doc-one", document_version="missing")
    assert store.count(tenant_id="demo", filters={"document_version": "v1"}, active_only=True) == 1
    store.upsert((new,), _batch((new,)))
    store.activate_version(document_id="doc-one", document_version="v2")
    assert store.count(tenant_id="demo", filters={"document_version": "v1"}, active_only=True) == 0
    assert store.count(tenant_id="demo", filters={"document_version": "v2"}, active_only=True) == 1


def test_qdrant_adapter_rejects_collection_model_or_dimension_change() -> None:
    client = QdrantClient(":memory:")
    _store(client)
    with pytest.raises(EmbeddingModelMismatchError):
        QdrantVectorStore(
            client,
            collection_name="unit",
            model_name="other-model",
            model_revision="revision-a",
            dimension=3,
        )
    with pytest.raises(VectorDimensionMismatchError):
        QdrantVectorStore(
            client,
            collection_name="unit",
            model_name="model-a",
            model_revision="revision-a",
            dimension=4,
        )
