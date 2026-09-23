"""Persistent vector-store adapters."""

from .qdrant import (
    CollectionConfigurationError,
    EmbeddingModelMismatchError,
    QdrantVectorStore,
    VectorDimensionMismatchError,
    VectorStoreError,
)

__all__ = [
    "CollectionConfigurationError",
    "EmbeddingModelMismatchError",
    "QdrantVectorStore",
    "VectorDimensionMismatchError",
    "VectorStoreError",
]
