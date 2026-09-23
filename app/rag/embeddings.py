from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.domain.models import EmbeddingBatch


class EmbeddingProviderError(RuntimeError):
    """Raised when a local embedding model cannot load or encode input."""


class SentenceTransformerEmbeddingProvider:
    """CPU-only Sentence-Transformers adapter with explicit model metadata."""

    def __init__(
        self,
        *,
        model_name: str,
        model_revision: str,
        normalize_embeddings: bool = True,
        batch_size: int = 8,
        model: Any | None = None,
        local_files_only: bool = False,
    ) -> None:
        if not model_name.strip() or not model_revision.strip():
            raise ValueError("model_name and model_revision are required")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self._model_name = model_name
        self._model_revision = model_revision
        self._normalize_embeddings = normalize_embeddings
        self._batch_size = batch_size
        try:
            self._model = model or self._load_model(local_files_only=local_files_only)
            dimension_method = getattr(self._model, "get_embedding_dimension", None)
            dimension_method = dimension_method or getattr(
                self._model, "get_sentence_embedding_dimension", None
            )
            if dimension_method is None:
                raise ValueError("model does not expose an embedding dimension")
            dimension = dimension_method()
            if not isinstance(dimension, int) or dimension < 1:
                raise ValueError("model returned an invalid embedding dimension")
            self._dimension = dimension
        except Exception as exc:
            raise EmbeddingProviderError(
                f"unable to load embedding model {model_name}@{model_revision}: {exc}"
            ) from exc

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_revision(self) -> str:
        return self._model_revision

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def normalized(self) -> bool:
        return self._normalize_embeddings

    @property
    def max_sequence_length(self) -> int:
        value = getattr(self._model, "max_seq_length", 0)
        return int(value) if value else 0

    def embed(self, texts: Sequence[str], *, chunk_ids: Sequence[str]) -> EmbeddingBatch:
        if not texts:
            raise ValueError("texts must not be empty")
        if len(texts) != len(chunk_ids):
            raise ValueError("texts and chunk_ids must have the same length")
        vectors = self._encode(texts, query=False)
        return EmbeddingBatch(
            model_name=self.model_name,
            model_revision=self.model_revision,
            dimension=self.dimension,
            chunk_ids=tuple(chunk_ids),
            vectors=vectors,
            normalized=self.normalized,
            device="cpu",
            dtype="float32",
        )

    def embed_queries(self, texts: Sequence[str]) -> tuple[tuple[float, ...], ...]:
        if not texts:
            raise ValueError("query texts must not be empty")
        return self._encode(texts, query=True)

    def count_tokens(self, text: str) -> int:
        """Count tokens with the loaded model tokenizer without truncation."""

        tokenizer = getattr(self._model, "tokenizer", None)
        if tokenizer is None:
            raise EmbeddingProviderError("loaded model does not expose a tokenizer")
        encoded = tokenizer(text, add_special_tokens=True, truncation=False)
        input_ids = encoded.get("input_ids")
        if not isinstance(input_ids, Sequence):
            raise EmbeddingProviderError("tokenizer returned invalid input_ids")
        return len(input_ids)

    def _load_model(self, *, local_files_only: bool) -> Any:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingProviderError(
                "sentence-transformers is not installed; install the embedding dependency group"
            ) from exc
        return SentenceTransformer(
            self.model_name,
            revision=self.model_revision,
            device="cpu",
            trust_remote_code=False,
            local_files_only=local_files_only,
        )

    def _encode(
        self,
        texts: Sequence[str],
        *,
        query: bool,
    ) -> tuple[tuple[float, ...], ...]:
        method_name = "encode_query" if query else "encode_document"
        encode = getattr(self._model, method_name, None) or getattr(self._model, "encode", None)
        if encode is None:
            raise EmbeddingProviderError(f"loaded model does not implement {method_name} or encode")
        try:
            raw_vectors = encode(
                list(texts),
                batch_size=self._batch_size,
                show_progress_bar=False,
                convert_to_numpy=True,
                normalize_embeddings=self._normalize_embeddings,
            )
            values = raw_vectors.tolist() if hasattr(raw_vectors, "tolist") else raw_vectors
            vectors = tuple(tuple(float(value) for value in vector) for vector in values)
        except Exception as exc:
            raise EmbeddingProviderError(
                f"embedding failed for {self.model_name}@{self.model_revision}: {exc}"
            ) from exc
        if len(vectors) != len(texts):
            raise EmbeddingProviderError("model returned a different number of vectors than inputs")
        if any(len(vector) != self.dimension for vector in vectors):
            raise EmbeddingProviderError("model returned a vector with an unexpected dimension")
        return vectors
