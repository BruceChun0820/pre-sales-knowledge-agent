from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from qdrant_client import QdrantClient, models

from app.domain.models import Chunk, EmbeddingBatch, TenantId

_NAMESPACE = uuid.UUID("a12a8c4d-28dc-4a45-bc15-159ce4d26a9d")
_INDEXED = {
    "tenant_id": models.PayloadSchemaType.KEYWORD,
    "active": models.PayloadSchemaType.BOOL,
    "industry": models.PayloadSchemaType.KEYWORD,
    "document_type": models.PayloadSchemaType.KEYWORD,
    "products": models.PayloadSchemaType.KEYWORD,
    "document_id": models.PayloadSchemaType.KEYWORD,
    "document_version": models.PayloadSchemaType.KEYWORD,
}
_FILTERS = frozenset(_INDEXED) - {"tenant_id"}
_CHUNK_FIELDS = frozenset(Chunk.model_fields)


class VectorStoreError(RuntimeError):
    """Base error for Qdrant adapter failures."""


class CollectionConfigurationError(VectorStoreError):
    """The collection schema differs from the configured schema."""


class EmbeddingModelMismatchError(VectorStoreError):
    """An operation attempts to mix model revisions in one collection."""


class VectorDimensionMismatchError(VectorStoreError):
    """A vector dimension differs from the collection dimension."""


class QdrantVectorStore:
    """Qdrant adapter that stores domain chunks and enforces query scope."""

    def __init__(
        self,
        client: QdrantClient,
        *,
        collection_name: str,
        model_name: str,
        model_revision: str,
        dimension: int,
        tenant_id: TenantId = "demo",
    ) -> None:
        if not collection_name.strip() or not model_name.strip() or not model_revision.strip():
            raise ValueError("collection name and embedding model metadata are required")
        if dimension < 1:
            raise ValueError("dimension must be positive")
        self._client = client
        self.collection_name = collection_name
        self.model_name = model_name
        self.model_revision = model_revision
        self.dimension = dimension
        self.tenant_id = tenant_id
        self._ensure_collection()

    @staticmethod
    def point_id(chunk_id: str) -> str:
        """Map stable chunk IDs to deterministic Qdrant UUIDs."""
        return str(uuid.uuid5(_NAMESPACE, chunk_id))

    def _ensure_collection(self) -> None:
        metadata = {
            "embedding_model": self.model_name,
            "embedding_model_revision": self.model_revision,
            "embedding_dimension": self.dimension,
        }
        try:
            if not self._client.collection_exists(self.collection_name):
                self._client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=self.dimension, distance=models.Distance.COSINE
                    ),
                    metadata=metadata,
                )
            info = self._client.get_collection(self.collection_name)
        except Exception as exc:
            raise VectorStoreError(f"unable to initialize Qdrant collection: {exc}") from exc
        vector_config = info.config.params.vectors
        if not isinstance(vector_config, models.VectorParams):
            raise CollectionConfigurationError("named-vector collections are not supported")
        if vector_config.size != self.dimension:
            raise VectorDimensionMismatchError(
                f"collection dimension {vector_config.size} does not match {self.dimension}"
            )
        existing_metadata = info.config.metadata or {}
        if existing_metadata and existing_metadata != metadata:
            raise EmbeddingModelMismatchError(
                "collection embedding model, revision, or dimension does not match"
            )
        if not existing_metadata:
            try:
                self._client.update_collection(
                    collection_name=self.collection_name, metadata=metadata
                )
            except Exception as exc:
                raise CollectionConfigurationError(
                    f"cannot persist collection embedding metadata: {exc}"
                ) from exc
        for field_name, schema in _INDEXED.items():
            try:
                self._client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name=field_name,
                    field_schema=schema,
                    wait=True,
                )
            except Exception as exc:
                raise VectorStoreError(f"cannot index payload field {field_name}: {exc}") from exc

    def upsert(self, chunks: Sequence[Chunk], embeddings: EmbeddingBatch) -> None:
        if not chunks:
            raise ValueError("chunks must not be empty")
        if tuple(chunk.chunk_id for chunk in chunks) != embeddings.chunk_ids:
            raise ValueError("chunk IDs and embedding IDs must match in order")
        if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
            raise ValueError("chunk IDs must be unique within an upsert batch")
        if embeddings.dimension != self.dimension:
            raise VectorDimensionMismatchError(
                "embedding batch dimension does not match collection"
            )
        if (embeddings.model_name, embeddings.model_revision) != (
            self.model_name,
            self.model_revision,
        ):
            raise EmbeddingModelMismatchError("embedding batch model/revision does not match")
        points = []
        for chunk, vector in zip(chunks, embeddings.vectors, strict=True):
            if chunk.tenant_id != self.tenant_id:
                raise ValueError("chunk tenant does not match configured tenant")
            if chunk.embedding_model not in (None, self.model_name):
                raise EmbeddingModelMismatchError(f"chunk {chunk.chunk_id} model does not match")
            if chunk.embedding_dimension not in (None, self.dimension):
                raise VectorDimensionMismatchError(
                    f"chunk {chunk.chunk_id} dimension does not match"
                )
            payload = chunk.model_copy(
                update={"embedding_model": self.model_name, "embedding_dimension": self.dimension}
            ).model_dump(mode="json")
            payload["embedding_model_revision"] = self.model_revision
            points.append(
                models.PointStruct(
                    id=self.point_id(chunk.chunk_id), vector=list(vector), payload=payload
                )
            )
        try:
            self._client.upsert(collection_name=self.collection_name, points=points, wait=True)
        except Exception as exc:
            raise VectorStoreError(f"Qdrant upsert failed: {exc}") from exc

    def search(
        self,
        query_vector: Sequence[float],
        *,
        tenant_id: TenantId,
        limit: int,
        filters: Mapping[str, object] | None = None,
    ) -> tuple[Chunk, ...]:
        if len(query_vector) != self.dimension:
            raise VectorDimensionMismatchError("query vector dimension does not match collection")
        if limit < 1:
            raise ValueError("limit must be positive")
        if tenant_id != self.tenant_id:
            return ()
        query_filter = self._filter(tenant_id, filters, active_default=True)
        try:
            points = self._client.query_points(
                collection_name=self.collection_name,
                query=list(query_vector),
                query_filter=query_filter,
                limit=limit,
                with_payload=True,
            ).points
        except Exception as exc:
            raise VectorStoreError(f"Qdrant search failed: {exc}") from exc
        return tuple(self._from_payload(point.payload or {}) for point in points)

    def count(
        self,
        *,
        tenant_id: TenantId,
        filters: Mapping[str, object] | None = None,
        active_only: bool | None = None,
    ) -> int:
        if tenant_id != self.tenant_id:
            return 0
        query_filter = self._filter(tenant_id, filters, active_default=active_only)
        try:
            return self._client.count(
                collection_name=self.collection_name, count_filter=query_filter, exact=True
            ).count
        except Exception as exc:
            raise VectorStoreError(f"Qdrant count failed: {exc}") from exc

    def activate_version(self, *, document_id: str, document_version: str) -> None:
        """Activate a verified version, then retire its older versions."""
        version_filter = {"document_id": document_id, "document_version": document_version}
        if not self.count(tenant_id=self.tenant_id, filters=version_filter):
            raise VectorStoreError(
                f"cannot activate missing version {document_id}@{document_version}"
            )
        self._set_active(version_filter, True)
        self._set_active({"document_id": document_id}, False, exclude_version=document_version)

    def _set_active(
        self,
        filters: Mapping[str, object],
        active: bool,
        *,
        exclude_version: str | None = None,
    ) -> None:
        selector = self._filter(self.tenant_id, filters, active_default=None)
        if exclude_version is not None:
            selector = models.Filter(
                must=selector.must,
                must_not=[
                    models.FieldCondition(
                        key="document_version",
                        match=models.MatchValue(value=exclude_version),
                    )
                ],
            )
        try:
            self._client.set_payload(
                collection_name=self.collection_name,
                payload={"active": active},
                points=selector,
                wait=True,
            )
        except Exception as exc:
            raise VectorStoreError(f"Qdrant activation failed: {exc}") from exc

    @staticmethod
    def _filter(
        tenant_id: TenantId,
        filters: Mapping[str, object] | None,
        *,
        active_default: bool | None,
    ) -> models.Filter:
        requested = dict(filters or {})
        unknown = set(requested) - _FILTERS
        if unknown:
            raise ValueError(f"unsupported vector filters: {', '.join(sorted(unknown))}")
        must = [models.FieldCondition(key="tenant_id", match=models.MatchValue(value=tenant_id))]
        if active_default is not None:
            if "active" in requested and requested["active"] != active_default:
                raise ValueError("active filter conflicts with required active state")
            requested["active"] = active_default
        for key, value in requested.items():
            if value is None:
                raise ValueError(f"filter {key} cannot be None")
            if isinstance(value, (list, tuple, set, frozenset)):
                values = list(value)
                if not values:
                    raise ValueError(f"filter {key} cannot be empty")
                match = models.MatchAny(any=values)
            else:
                match = models.MatchValue(value=value)
            must.append(models.FieldCondition(key=key, match=match))
        return models.Filter(must=must)

    @staticmethod
    def _from_payload(payload: Mapping[str, Any]) -> Chunk:
        try:
            return Chunk.model_validate(
                {key: value for key, value in payload.items() if key in _CHUNK_FIELDS}
            )
        except Exception as exc:
            raise VectorStoreError(f"Qdrant returned an invalid chunk payload: {exc}") from exc
