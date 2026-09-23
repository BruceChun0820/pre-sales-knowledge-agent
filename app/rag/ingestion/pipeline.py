from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.domain.interfaces import ChunkingStrategy, EmbeddingProvider, TextCleaner
from app.domain.models import (
    Confidentiality,
    DocumentRecord,
    DocumentType,
    IngestionError,
    IngestionErrorCode,
    Language,
    ParsedBlock,
)
from app.rag.chunking import ChunkingConfig, RegexTokenCounter, StructureAwareChunker
from app.rag.cleaning import ConservativeTextCleaner
from app.rag.embeddings import EmbeddingProviderError
from app.rag.parsing.registry import default_parser_registry
from app.rag.vector_store.qdrant import QdrantVectorStore, VectorStoreError

from .discovery import DiscoveredFile, FileDiscovery
from .manifest import ManifestEntry, ManifestStatus, ManifestStore, update_manifest_entry
from .service import ParserService


class DocumentMetadata(BaseModel):
    """Explicit, non-inferred metadata for a relative source path."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    document_type: DocumentType
    confidentiality: Confidentiality
    industry: tuple[str, ...] = ()
    products: tuple[str, ...] = ()
    language: Language = Language.UNKNOWN
    published_at: date | None = None


@dataclass(frozen=True)
class IngestionSummary:
    discovered: int
    parsed: int
    chunked: int
    embedded: int
    upserted: int
    skipped: int
    failed: int
    errors: tuple[IngestionError, ...]

    def to_dict(self) -> dict[str, Any]:
        values = asdict(self)
        values["errors"] = [error.model_dump(mode="json") for error in self.errors]
        return values


class IngestionPipeline:
    """Run discovery through safe, per-document Qdrant activation."""

    def __init__(
        self,
        *,
        discovery: FileDiscovery,
        manifest: ManifestStore,
        vector_store: QdrantVectorStore,
        embedding_provider: EmbeddingProvider,
        cleaner: TextCleaner | None = None,
        chunker: ChunkingStrategy | None = None,
    ) -> None:
        self.discovery = discovery
        self.manifest = manifest
        self.vector_store = vector_store
        self.embedding_provider = embedding_provider
        self.cleaner = cleaner or ConservativeTextCleaner()
        self.chunker = chunker or StructureAwareChunker(
            token_counter=RegexTokenCounter(),
            config=ChunkingConfig(),
        )
        self.parser = ParserService(default_parser_registry(), manifest_store=manifest)

    def run(self, metadata_by_path: Mapping[str, DocumentMetadata]) -> IngestionSummary:
        discovered = self.discovery.discover()
        errors = list(discovered.failures)
        counts = dict(parsed=0, chunked=0, embedded=0, upserted=0, skipped=0)
        for item in discovered.files:
            raw_metadata = metadata_by_path.get(item.relative_path)
            if raw_metadata is None:
                error = self._error(
                    IngestionErrorCode.INVALID_INPUT,
                    "explicit metadata is missing for this relative path",
                    item.document_id,
                    item.relative_path,
                )
                self._record_error(item, error)
                errors.append(error)
                continue
            try:
                metadata = (
                    raw_metadata
                    if isinstance(raw_metadata, DocumentMetadata)
                    else DocumentMetadata.model_validate(raw_metadata)
                )
            except ValidationError as exc:
                error = self._error(
                    IngestionErrorCode.VALIDATION_FAILED,
                    str(exc),
                    item.document_id,
                    item.relative_path,
                )
                self._record_error(item, error)
                errors.append(error)
                continue

            try:
                if self._is_unchanged(item):
                    counts["skipped"] += 1
                    continue
            except VectorStoreError as exc:
                error = self._error(
                    IngestionErrorCode.VECTOR_STORE_FAILED,
                    str(exc),
                    item.document_id,
                    item.relative_path,
                )
                self._record_error(item, error)
                errors.append(error)
                continue
            document = self._document(item, metadata)
            outcome = self.parser.parse_batch(((item, document),))[0]
            if outcome.error is not None:
                errors.append(outcome.error)
                continue
            counts["parsed"] += 1
            try:
                result = self._ingest_document(item, document, outcome.blocks)
                for key, value in result.items():
                    counts[key] += value
            except Exception as exc:
                code = (
                    IngestionErrorCode.VECTOR_STORE_FAILED
                    if isinstance(exc, VectorStoreError)
                    else IngestionErrorCode.EMBEDDING_FAILED
                    if isinstance(exc, EmbeddingProviderError)
                    else IngestionErrorCode.UNKNOWN
                )
                error = self._error(code, str(exc), item.document_id, item.relative_path)
                self._record_error(item, error)
                errors.append(error)
        failed = len(errors)
        return IngestionSummary(
            discovered=len(discovered.files) + len(discovered.failures),
            parsed=counts["parsed"],
            chunked=counts["chunked"],
            embedded=counts["embedded"],
            upserted=counts["upserted"],
            skipped=counts["skipped"],
            failed=failed,
            errors=tuple(errors),
        )

    def _is_unchanged(self, item: DiscoveredFile) -> bool:
        current = self.manifest.get(item.document_id, item.document_version)
        if current is None or current.status is not ManifestStatus.ACTIVE:
            return False
        return (
            self.vector_store.count(
                tenant_id=self.vector_store.tenant_id,
                filters={
                    "document_id": item.document_id,
                    "document_version": item.document_version,
                },
                active_only=True,
            )
            > 0
        )

    @staticmethod
    def _document(item: DiscoveredFile, metadata: DocumentMetadata) -> DocumentRecord:
        return DocumentRecord(
            document_id=item.document_id,
            document_version=item.document_version,
            title=metadata.title,
            source_uri=item.relative_path,
            document_type=metadata.document_type,
            industry=metadata.industry,
            products=metadata.products,
            language=metadata.language,
            published_at=metadata.published_at,
            active=False,
            confidentiality=metadata.confidentiality,
            content_checksum=item.content_checksum,
        )

    def _ingest_document(
        self, item: DiscoveredFile, document: DocumentRecord, blocks: tuple[ParsedBlock, ...]
    ) -> dict[str, int]:
        cleaned = tuple(self.cleaner.clean(blocks))
        chunks = tuple(
            self.chunker.chunk(cleaned, document=document, cleaner_version=self.cleaner.version)
        )
        if not chunks:
            raise ValueError("document produced no non-empty chunks")
        self._update_manifest(item, ManifestStatus.CHUNKED)
        embeddings = self.embedding_provider.embed(
            tuple(chunk.text for chunk in chunks),
            chunk_ids=tuple(chunk.chunk_id for chunk in chunks),
        )
        self.vector_store.upsert(chunks, embeddings)
        version_filter = {
            "document_id": document.document_id,
            "document_version": document.document_version,
        }
        stored = self.vector_store.count(
            tenant_id=document.tenant_id, filters=version_filter, active_only=False
        )
        if stored != len(chunks):
            raise VectorStoreError(
                f"staged point count mismatch: expected {len(chunks)}, found {stored}"
            )
        self._update_manifest(item, ManifestStatus.INDEXED)
        self.vector_store.activate_version(
            document_id=document.document_id,
            document_version=document.document_version,
        )
        self._update_manifest(item, ManifestStatus.ACTIVE)
        for previous in self.manifest.load():
            if (
                previous.document_id == item.document_id
                and previous.document_version != item.document_version
                and previous.status is ManifestStatus.ACTIVE
            ):
                self.manifest.upsert(update_manifest_entry(previous, status=ManifestStatus.INDEXED))
        return {"chunked": len(chunks), "embedded": len(embeddings.vectors), "upserted": stored}

    def _update_manifest(self, item: DiscoveredFile, status: ManifestStatus) -> None:
        current = self.manifest.get(item.document_id, item.document_version)
        if current is None:
            current = ManifestEntry.from_discovered_file(item)
        self.manifest.upsert(update_manifest_entry(current, status=status))

    def _record_error(self, item: DiscoveredFile, error: IngestionError) -> None:
        current = self.manifest.get(item.document_id, item.document_version)
        if current is None:
            current = ManifestEntry.from_discovered_file(item)
        self.manifest.upsert(
            update_manifest_entry(current, status=ManifestStatus.FAILED, error=error)
        )

    @staticmethod
    def _error(
        code: IngestionErrorCode, message: str, document_id: str, source_uri: str
    ) -> IngestionError:
        return IngestionError(
            code=code,
            message=message or code.value,
            document_id=document_id,
            source_uri=source_uri,
        )
