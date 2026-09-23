from __future__ import annotations

import hashlib
import uuid

from qdrant_client import QdrantClient

from app.domain.contracts import SearchRequest, SearchStatus
from app.domain.models import (
    Chunk,
    Confidentiality,
    DocumentType,
    EmbeddingBatch,
    Language,
    SourceLocation,
)
from app.rag.retrieval import DenseRetriever
from app.rag.vector_store import QdrantVectorStore


class FixtureEmbeddingProvider:
    model_name = "fixture-model"
    model_revision = "fixture-revision"
    dimension = 3

    vectors = {
        "What does model P-42 exclude?": (1.0, 0.0, 0.0),
        "P-42 excludes offshore hosting.": (1.0, 0.0, 0.0),
        "P-42 does not exclude encrypted backups.": (0.8, 0.6, 0.0),
        "Healthcare-only retention policy.": (0.0, 1.0, 0.0),
    }

    def embed_queries(self, texts):
        return tuple(self.vectors[text] for text in texts)

    def embed(self, texts, *, chunk_ids):
        return EmbeddingBatch(
            model_name=self.model_name,
            model_revision=self.model_revision,
            dimension=self.dimension,
            chunk_ids=tuple(chunk_ids),
            vectors=tuple(self.vectors[text] for text in texts),
        )


def _chunk(
    chunk_id: str,
    text: str,
    *,
    active: bool,
    industry: tuple[str, ...],
    document_version: str = "v1",
) -> Chunk:
    return Chunk(
        document_id="doc-" + chunk_id,
        document_version=document_version,
        chunk_id=chunk_id,
        text=text,
        text_checksum=hashlib.sha256(text.encode()).hexdigest(),
        source_location=SourceLocation(page_start=1, page_end=1),
        title="Synthetic " + chunk_id,
        source_uri="samples/" + chunk_id + ".md",
        document_type=DocumentType.PRODUCT_GUIDE,
        industry=industry,
        products=("P-42",),
        language=Language.EN,
        active=active,
        confidentiality=Confidentiality.SYNTHETIC,
        section_path=("Limits",),
        chunk_index=0,
        parser_version="parser-v1",
        cleaner_version="cleaner-v1",
        chunker_version="chunker-v1",
        embedding_model=FixtureEmbeddingProvider.model_name,
        embedding_dimension=FixtureEmbeddingProvider.dimension,
        content_checksum=hashlib.sha256(b"source").hexdigest(),
    )


def test_qdrant_dense_search_is_ranked_filtered_and_scope_safe() -> None:
    client = QdrantClient(":memory:")
    collection = "phase2_retrieval_" + uuid.uuid4().hex[:12]
    store = QdrantVectorStore(
        client,
        collection_name=collection,
        model_name=FixtureEmbeddingProvider.model_name,
        model_revision=FixtureEmbeddingProvider.model_revision,
        dimension=FixtureEmbeddingProvider.dimension,
    )
    chunks = (
        _chunk(
            "exact",
            "P-42 excludes offshore hosting.",
            active=True,
            industry=("finance",),
        ),
        _chunk(
            "near",
            "P-42 does not exclude encrypted backups.",
            active=True,
            industry=("finance",),
        ),
        _chunk(
            "wrong-scope",
            "Healthcare-only retention policy.",
            active=True,
            industry=("healthcare",),
        ),
        _chunk(
            "inactive",
            "P-42 excludes offshore hosting.",
            active=False,
            industry=("finance",),
            document_version="v0",
        ),
    )
    vectors = tuple(FixtureEmbeddingProvider.vectors[chunk.text] for chunk in chunks)
    store.upsert(
        chunks,
        EmbeddingBatch(
            model_name=FixtureEmbeddingProvider.model_name,
            model_revision=FixtureEmbeddingProvider.model_revision,
            dimension=FixtureEmbeddingProvider.dimension,
            chunk_ids=tuple(chunk.chunk_id for chunk in chunks),
            vectors=vectors,
            normalized=True,
        ),
    )
    store.activate_version(document_id="doc-exact", document_version="v1")
    store.activate_version(document_id="doc-near", document_version="v1")
    store.activate_version(document_id="doc-wrong-scope", document_version="v1")

    retriever = DenseRetriever(FixtureEmbeddingProvider(), store)
    request = SearchRequest(
        query="What does model P-42 exclude?",
        top_k=4,
        filters={"industry": ["finance"]},
    )

    first = retriever.search(request, request_id="qdrant-1")
    second = retriever.search(request, request_id="qdrant-1")

    assert first.status == SearchStatus.SUCCEEDED
    assert [hit.chunk_id for hit in first.hits] == ["exact", "near"]
    assert [hit.score for hit in first.hits] == [1.0, 0.8]
    assert all(hit.rank == index for index, hit in enumerate(first.hits, start=1))
    assert all(hit.document_id in {"doc-exact", "doc-near"} for hit in first.hits)
    assert all(hit.document_version == "v1" for hit in first.hits)
    assert [hit.model_dump(mode="json") for hit in first.hits] == [
        hit.model_dump(mode="json") for hit in second.hits
    ]


def test_qdrant_dense_search_honors_positive_and_negative_filters() -> None:
    client = QdrantClient(":memory:")
    collection = "phase2_filters_" + uuid.uuid4().hex[:12]
    store = QdrantVectorStore(
        client,
        collection_name=collection,
        model_name=FixtureEmbeddingProvider.model_name,
        model_revision=FixtureEmbeddingProvider.model_revision,
        dimension=FixtureEmbeddingProvider.dimension,
    )
    chunks = (
        _chunk(
            "finance",
            "P-42 excludes offshore hosting.",
            active=True,
            industry=("finance",),
        ),
        _chunk(
            "healthcare",
            "Healthcare-only retention policy.",
            active=True,
            industry=("healthcare",),
        ),
    )
    store.upsert(
        chunks,
        EmbeddingBatch(
            model_name=FixtureEmbeddingProvider.model_name,
            model_revision=FixtureEmbeddingProvider.model_revision,
            dimension=FixtureEmbeddingProvider.dimension,
            chunk_ids=tuple(chunk.chunk_id for chunk in chunks),
            vectors=tuple(FixtureEmbeddingProvider.vectors[chunk.text] for chunk in chunks),
            normalized=True,
        ),
    )
    for chunk in chunks:
        store.activate_version(document_id=chunk.document_id, document_version="v1")

    retriever = DenseRetriever(FixtureEmbeddingProvider(), store)
    scoped = retriever.search(
        SearchRequest(
            query="What does model P-42 exclude?",
            top_k=5,
            filters={"industry": ["healthcare"]},
        ),
        request_id="positive-filter",
    )
    assert scoped.status == SearchStatus.SUCCEEDED
    assert [hit.document_id for hit in scoped.hits] == ["doc-healthcare"]
    assert all("healthcare" in hit.source_uri for hit in scoped.hits)

    no_match = retriever.search(
        SearchRequest(
            query="What does model P-42 exclude?",
            top_k=5,
            filters={"industry": ["finance"], "document_type": "rfp"},
        ),
        request_id="negative-filter",
    )
    assert no_match.status == SearchStatus.EMPTY
    assert no_match.hits == ()
