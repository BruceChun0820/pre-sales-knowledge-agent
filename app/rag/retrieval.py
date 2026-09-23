from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import fsum, sqrt
from time import perf_counter
from typing import Protocol

from app.domain.contracts import (
    Failure,
    FailureCode,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SearchService,
    SearchStatus,
    TraceMetadata,
)
from app.domain.interfaces import VectorStore
from app.domain.models import Chunk, EmbeddingBatch, TenantId
from app.rag.query_processing import QueryProcessor


class QueryEmbeddingProvider(Protocol):
    """Embedding adapter capabilities required for asymmetric dense query matching."""

    @property
    def model_name(self) -> str: ...

    @property
    def model_revision(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    def embed_queries(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...

    def embed(self, texts: Sequence[str], *, chunk_ids: Sequence[str]) -> EmbeddingBatch: ...


@dataclass(frozen=True)
class RetrievalScope:
    """System-owned scope injected into every search request."""

    tenant_id: TenantId = "demo"
    document_id: str | None = None
    document_version: str | None = None

    def __post_init__(self) -> None:
        if self.document_version is not None and self.document_id is None:
            raise ValueError("a required document version must include its document ID")
        for name, value in (
            ("document_id", self.document_id),
            ("document_version", self.document_version),
        ):
            if value is not None and not value.strip():
                raise ValueError(f"{name} cannot be empty")


class DenseRetriever(SearchService):
    """Dense retrieval through the accepted embedding and vector-store boundaries.

    QdrantVectorStore returns domain chunks but currently discards Qdrant point scores.
    The bounded result set is therefore re-embedded through the same model revision and
    scored with cosine similarity, matching the collection's metric without depending on
    Qdrant SDK types or modifying the accepted adapter.
    """

    def __init__(
        self,
        embedding_provider: QueryEmbeddingProvider,
        vector_store: VectorStore,
        *,
        query_processor: QueryProcessor | None = None,
        scope: RetrievalScope | None = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._query_processor = query_processor or QueryProcessor()
        self._scope = scope or RetrievalScope()

    def search(self, request: SearchRequest, *, request_id: str) -> SearchResponse:
        started = perf_counter()
        normalized_query = self._query_processor.normalize(request.query)
        if not normalized_query:
            return self._failed(
                request_id,
                FailureCode.VALIDATION_ERROR,
                "query is empty after normalization",
                started,
            )

        filters, scope_failure = self._filters_for(request)
        if scope_failure is not None:
            return self._failed(
                request_id,
                FailureCode.VALIDATION_ERROR,
                scope_failure,
                started,
            )

        try:
            query_vectors = self._embedding_provider.embed_queries([normalized_query])
            if len(query_vectors) != 1:
                raise ValueError("embedding provider returned an unexpected query count")
            query_vector = tuple(float(value) for value in query_vectors[0])
            self._validate_vector(query_vector, self._embedding_provider.dimension)
        except Exception:
            return self._failed(
                request_id,
                FailureCode.PROVIDER_FAILURE,
                "query embedding failed",
                started,
                stage="query_embedding",
            )

        try:
            chunks = tuple(
                self._vector_store.search(
                    query_vector,
                    tenant_id=self._scope.tenant_id,
                    limit=request.top_k,
                    filters=filters,
                )
            )
        except Exception:
            return self._failed(
                request_id,
                FailureCode.RETRIEVAL_UNAVAILABLE,
                "vector search failed",
                started,
                stage="vector_search",
            )

        if not chunks:
            return SearchResponse(
                status=SearchStatus.EMPTY,
                trace=self._trace(request_id, started),
            )

        try:
            doc_vectors = self._embedding_provider.embed(
                [chunk.text for chunk in chunks],
                chunk_ids=[chunk.chunk_id for chunk in chunks],
            )
            self._validate_embedding_batch(chunks, doc_vectors)
            scored = [
                (self._cosine_similarity(query_vector, vector), chunk)
                for chunk, vector in zip(chunks, doc_vectors.vectors, strict=True)
            ]
        except Exception:
            return self._failed(
                request_id,
                FailureCode.PROVIDER_FAILURE,
                "candidate scoring failed",
                started,
                stage="candidate_scoring",
            )

        # Preserve the vector store order; cosine values only populate score metadata.
        hits = tuple(
            SearchHit.from_chunk(chunk, rank=rank, score=score)
            for rank, (score, chunk) in enumerate(scored, start=1)
        )
        return SearchResponse(
            status=SearchStatus.SUCCEEDED,
            hits=hits,
            trace=self._trace(request_id, started),
        )

    def _filters_for(self, request: SearchRequest) -> tuple[Mapping[str, object], str | None]:
        filters = request.filters
        resolved: dict[str, object] = {}
        if filters.industry:
            resolved["industry"] = filters.industry
        if filters.document_type is not None:
            resolved["document_type"] = filters.document_type.value
        if filters.products:
            resolved["products"] = filters.products
        if filters.document_id is not None:
            resolved["document_id"] = filters.document_id
        if filters.document_version is not None:
            resolved["document_version"] = filters.document_version

        for key, required in (
            ("document_id", self._scope.document_id),
            ("document_version", self._scope.document_version),
        ):
            if required is not None and key in resolved and resolved[key] != required:
                return {}, f"request {key} conflicts with required system scope"
            if required is not None:
                resolved[key] = required
        return resolved, None

    def _validate_embedding_batch(self, chunks: Sequence[Chunk], batch: EmbeddingBatch) -> None:
        provider = self._embedding_provider
        if (
            batch.model_name != provider.model_name
            or batch.model_revision != provider.model_revision
            or batch.dimension != provider.dimension
        ):
            raise ValueError("candidate embedding identity differs from query model")
        if batch.chunk_ids != tuple(chunk.chunk_id for chunk in chunks):
            raise ValueError("candidate embedding order differs from search result order")
        for chunk in chunks:
            if chunk.embedding_model not in (None, provider.model_name):
                raise ValueError("candidate chunk model differs from query model")
            if chunk.embedding_dimension not in (None, provider.dimension):
                raise ValueError("candidate chunk dimension differs from query model")

    @staticmethod
    def _validate_vector(vector: Sequence[float], dimension: int) -> None:
        if len(vector) != dimension or not vector:
            raise ValueError("embedding dimension mismatch")
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("embedding contains a non-finite value")

    @staticmethod
    def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
        if len(left) != len(right) or not left:
            raise ValueError("vectors must have the same non-zero dimension")
        left_norm = sqrt(fsum(value * value for value in left))
        right_norm = sqrt(fsum(value * value for value in right))
        if left_norm == 0 or right_norm == 0:
            raise ValueError("cosine similarity is undefined for a zero vector")
        score = fsum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
        return max(-1.0, min(1.0, score))

    @staticmethod
    def _trace(request_id: str, started: float) -> TraceMetadata:
        return TraceMetadata(
            request_id=request_id,
            latency_ms=(perf_counter() - started) * 1000,
        )

    def _failed(
        self,
        request_id: str,
        code: FailureCode,
        message: str,
        started: float,
        *,
        stage: str | None = None,
    ) -> SearchResponse:
        details = {"stage": stage} if stage is not None else {}
        return SearchResponse(
            status=SearchStatus.FAILED,
            trace=self._trace(request_id, started),
            failure=Failure(code=code, message=message, details=details),
        )
