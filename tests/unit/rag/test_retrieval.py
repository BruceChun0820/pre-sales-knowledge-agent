from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

import pytest

from app.domain.contracts import FailureCode, SearchRequest, SearchStatus
from app.domain.interfaces import VectorStore
from app.domain.models import (
    Chunk,
    Confidentiality,
    DocumentType,
    EmbeddingBatch,
    Language,
    SourceLocation,
)
from app.rag.retrieval import DenseRetriever, RetrievalScope


def _chunk(
    chunk_id: str,
    text: str,
    *,
    active: bool = True,
    industry: tuple[str, ...] = ("finance",),
    document_version: str = "v1",
) -> Chunk:
    digest = hashlib.sha256(text.encode()).hexdigest()
    source_digest = hashlib.sha256(b"source").hexdigest()
    return Chunk(
        document_id="doc-one",
        document_version=document_version,
        chunk_id=chunk_id,
        text=text,
        text_checksum=digest,
        source_location=SourceLocation(page_start=1, page_end=1),
        title="Synthetic guide",
        source_uri="samples/guide.md",
        document_type=DocumentType.PRODUCT_GUIDE,
        industry=industry,
        products=("Agent X",),
        language=Language.EN,
        active=active,
        confidentiality=Confidentiality.SYNTHETIC,
        section_path=("Overview",),
        chunk_index=0,
        parser_version="parser-v1",
        cleaner_version="cleaner-v1",
        chunker_version="chunker-v1",
        embedding_model="test-model",
        embedding_dimension=2,
        content_checksum=source_digest,
    )


class FakeEmbeddingProvider:
    model_name = "test-model"
    model_revision = "revision-1"
    dimension = 2

    def __init__(self, vectors: Mapping[str, Sequence[float]]) -> None:
        self.vectors = {key: tuple(value) for key, value in vectors.items()}
        self.queries: list[str] = []
        self.document_batches: list[tuple[str, ...]] = []

    def embed_queries(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        self.queries.extend(texts)
        return tuple(self.vectors[text] for text in texts)

    def embed(self, texts: Sequence[str], *, chunk_ids: Sequence[str]) -> EmbeddingBatch:
        self.document_batches.append(tuple(texts))
        return EmbeddingBatch(
            model_name=self.model_name,
            model_revision=self.model_revision,
            dimension=self.dimension,
            chunk_ids=tuple(chunk_ids),
            vectors=tuple(self.vectors[text] for text in texts),
        )


class FakeVectorStore(VectorStore):
    def __init__(self, chunks: Sequence[Chunk], *, error: Exception | None = None) -> None:
        self.chunks = tuple(chunks)
        self.error = error
        self.calls: list[dict[str, object]] = []

    def upsert(self, chunks, embeddings) -> None:
        raise NotImplementedError

    def search(
        self,
        query_vector: Sequence[float],
        *,
        tenant_id: str,
        limit: int,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Chunk]:
        self.calls.append(
            {
                "query_vector": tuple(query_vector),
                "tenant_id": tenant_id,
                "limit": limit,
                "filters": dict(filters or {}),
            }
        )
        if self.error is not None:
            raise self.error
        return self.chunks[:limit]


def test_dense_retriever_scores_and_sorts_candidates_deterministically() -> None:
    query = "policy question"
    exact = _chunk("chunk-z", "exact evidence")
    near = _chunk("chunk-b", "near evidence")
    orthogonal = _chunk("chunk-a", "orthogonal evidence")
    encoder = FakeEmbeddingProvider(
        {
            query: (1.0, 0.0),
            exact.text: (2.0, 0.0),
            near.text: (0.6, 0.8),
            orthogonal.text: (0.0, 1.0),
        }
    )
    store = FakeVectorStore((exact, near, orthogonal))
    retriever = DenseRetriever(encoder, store)
    request = SearchRequest(query=query, top_k=3)

    first = retriever.search(request, request_id="req-1")
    second = retriever.search(request, request_id="req-1")

    assert first.status == SearchStatus.SUCCEEDED
    assert [(hit.rank, hit.chunk_id, hit.score) for hit in first.hits] == [
        (1, "chunk-z", pytest.approx(1.0)),
        (2, "chunk-b", pytest.approx(0.6)),
        (3, "chunk-a", pytest.approx(0.0)),
    ]
    assert [hit.model_dump(mode="json") for hit in first.hits] == [
        hit.model_dump(mode="json") for hit in second.hits
    ]
    assert len(encoder.document_batches) == 2


def test_dense_retriever_applies_explicit_filters_and_system_scope() -> None:
    chunk = _chunk("chunk-1", "evidence", document_version="v2")
    encoder = FakeEmbeddingProvider({"query": (1.0, 0.0), chunk.text: (1.0, 0.0)})
    store = FakeVectorStore((chunk,))
    retriever = DenseRetriever(
        encoder,
        store,
        scope=RetrievalScope(document_id="doc-one", document_version="v2"),
    )

    result = retriever.search(
        SearchRequest(
            query="query",
            filters={
                "industry": ["finance"],
                "document_type": "product_guide",
                "products": ["Agent X"],
            },
        ),
        request_id="req-2",
    )

    assert result.status == SearchStatus.SUCCEEDED
    assert store.calls[0]["tenant_id"] == "demo"
    assert store.calls[0]["filters"] == {
        "industry": ("finance",),
        "document_type": "product_guide",
        "products": ("Agent X",),
        "document_id": "doc-one",
        "document_version": "v2",
    }


def test_request_cannot_override_system_document_version_scope() -> None:
    encoder = FakeEmbeddingProvider({"query": (1.0, 0.0)})
    store = FakeVectorStore(())
    retriever = DenseRetriever(
        encoder,
        store,
        scope=RetrievalScope(document_id="doc-one", document_version="v2"),
    )

    result = retriever.search(
        SearchRequest(query="query", filters={"document_version": "v1"}),
        request_id="req-3",
    )

    assert result.status == SearchStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == FailureCode.VALIDATION_ERROR
    assert store.calls == []


def test_dense_retriever_returns_typed_empty_and_dependency_failures() -> None:
    empty = DenseRetriever(
        FakeEmbeddingProvider({"query": (1.0, 0.0)}), FakeVectorStore(())
    ).search(SearchRequest(query="query"), request_id="req-empty")
    assert empty.status == SearchStatus.EMPTY

    unavailable = DenseRetriever(
        FakeEmbeddingProvider({"query": (1.0, 0.0)}),
        FakeVectorStore((), error=RuntimeError("private backend detail")),
    ).search(SearchRequest(query="query"), request_id="req-store-fail")
    assert unavailable.status == SearchStatus.FAILED
    assert unavailable.failure is not None
    assert unavailable.failure.code == FailureCode.RETRIEVAL_UNAVAILABLE
    assert "private backend detail" not in unavailable.failure.message

    embedder = FakeEmbeddingProvider({"query": (1.0, 0.0)})
    embedder.embed_queries = lambda texts: (_ for _ in ()).throw(RuntimeError("private"))
    provider_failed = DenseRetriever(embedder, FakeVectorStore(())).search(
        SearchRequest(query="query"), request_id="req-embed-fail"
    )
    assert provider_failed.status == SearchStatus.FAILED
    assert provider_failed.failure is not None
    assert provider_failed.failure.code == FailureCode.PROVIDER_FAILURE


def test_dense_retriever_fails_closed_on_model_mismatch_and_zero_vectors() -> None:
    chunk = _chunk("chunk-1", "evidence")
    encoder = FakeEmbeddingProvider({"query": (1.0, 0.0), chunk.text: (0.0, 0.0)})
    mismatch = _chunk("chunk-2", "wrong model").model_copy(
        update={"embedding_model": "other-model"}
    )
    store = FakeVectorStore((mismatch,))
    result = DenseRetriever(
        FakeEmbeddingProvider({"query": (1.0, 0.0), mismatch.text: (1.0, 0.0)}), store
    ).search(SearchRequest(query="query"), request_id="req-mismatch")
    assert result.status == SearchStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == FailureCode.PROVIDER_FAILURE

    zero_result = DenseRetriever(encoder, FakeVectorStore((chunk,))).search(
        SearchRequest(query="query"), request_id="req-zero"
    )
    assert zero_result.status == SearchStatus.FAILED
    assert zero_result.failure is not None
    assert zero_result.failure.code == FailureCode.PROVIDER_FAILURE
