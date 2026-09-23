from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Protocol

from .models import Chunk, DocumentRecord, EmbeddingBatch, ParsedBlock, TenantId


class DocumentParser(Protocol):
    """Parse one approved source document into ordered, traceable blocks."""

    @property
    def name(self) -> str:
        """Return the stable parser name recorded in the manifest."""

    @property
    def version(self) -> str:
        """Return the parser implementation version."""

    def parse(self, source_path: Path, *, document: DocumentRecord) -> Iterable[ParsedBlock]:
        """Parse a source path without exposing parser SDK types to callers."""


class TextCleaner(Protocol):
    """Normalize parsed text conservatively without changing source meaning."""

    @property
    def name(self) -> str:
        """Return the stable cleaner name."""

    @property
    def version(self) -> str:
        """Return the cleaner implementation version."""

    def clean(self, blocks: Sequence[ParsedBlock]) -> Sequence[ParsedBlock]:
        """Return ordered blocks with deterministic text normalization."""


class ChunkingStrategy(Protocol):
    """Convert parsed blocks into deterministic, source-preserving chunks."""

    @property
    def name(self) -> str:
        """Return the stable chunking strategy name."""

    @property
    def version(self) -> str:
        """Return the chunking strategy version."""

    def chunk(
        self,
        blocks: Sequence[ParsedBlock],
        *,
        document: DocumentRecord,
        cleaner_version: str,
    ) -> Sequence[Chunk]:
        """Chunk ordered blocks without changing their source meaning or provenance."""


class EmbeddingProvider(Protocol):
    """Create a versioned batch of vectors for chunk text."""

    @property
    def model_name(self) -> str:
        """Return the model identifier used for the batch."""

    @property
    def model_revision(self) -> str:
        """Return the immutable model revision or snapshot identifier."""

    @property
    def dimension(self) -> int:
        """Return the vector dimension produced by this provider."""

    def embed(self, texts: Sequence[str], *, chunk_ids: Sequence[str]) -> EmbeddingBatch:
        """Embed texts in input order and return vectors with matching chunk IDs."""


class VectorStore(Protocol):
    """Persist and search domain chunks without leaking a storage SDK type."""

    def upsert(self, chunks: Sequence[Chunk], embeddings: EmbeddingBatch) -> None:
        """Insert or replace chunks whose vector dimensions match the batch."""

    def search(
        self,
        query_vector: Sequence[float],
        *,
        tenant_id: TenantId,
        limit: int,
        filters: Mapping[str, object] | None = None,
    ) -> Sequence[Chunk]:
        """Search active tenant-scoped chunks and return domain objects only."""
