from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.models import DocumentRecord, IngestionError, IngestionErrorCode, ParsedBlock
from app.rag.parsing.base import ParserRegistry
from app.rag.parsing.errors import ParserError

from .discovery import DiscoveredFile
from .manifest import ManifestEntry, ManifestStatus, ManifestStore, update_manifest_entry


@dataclass(frozen=True)
class ParseOutcome:
    """One document's successful blocks or typed isolated failure."""

    discovered: DiscoveredFile
    document: DocumentRecord
    blocks: tuple[ParsedBlock, ...]
    error: IngestionError | None = None


class ParserService:
    """Parse a batch while isolating failures and updating the manifest."""

    def __init__(
        self,
        registry: ParserRegistry,
        *,
        manifest_store: ManifestStore | None = None,
    ) -> None:
        self.registry = registry
        self.manifest_store = manifest_store

    def parse_batch(
        self,
        items: Sequence[tuple[DiscoveredFile, DocumentRecord]],
    ) -> tuple[ParseOutcome, ...]:
        outcomes: list[ParseOutcome] = []
        for discovered, document in items:
            outcomes.append(self._parse_one(discovered, document))
        return tuple(outcomes)

    def _parse_one(self, discovered: DiscoveredFile, document: DocumentRecord) -> ParseOutcome:
        manifest = ManifestEntry.from_discovered_file(discovered)
        if self.manifest_store is not None:
            self.manifest_store.upsert(manifest)

        if (
            document.document_id != discovered.document_id
            or document.document_version != discovered.document_version
            or document.content_checksum != discovered.content_checksum
        ):
            error = IngestionError(
                code=IngestionErrorCode.INVALID_INPUT,
                message="document identity does not match the discovered file",
                document_id=discovered.document_id,
                source_uri=discovered.relative_path,
            )
            self._record_failure(manifest, error, status=ManifestStatus.FAILED)
            return ParseOutcome(discovered, document, (), error)

        try:
            parser = self.registry.for_path(discovered.path)
            blocks = tuple(parser.parse(discovered.path, document=document))
            if not blocks:
                raise ParserError("parser returned no non-empty blocks")
            updated = update_manifest_entry(
                manifest,
                status=ManifestStatus.PARSED,
                parser_name=parser.name,
                parser_version=parser.version,
            )
            if self.manifest_store is not None:
                self.manifest_store.upsert(updated)
            return ParseOutcome(discovered, document, blocks)
        except ParserError as exc:
            error = IngestionError(
                code=exc.code,
                message=str(exc),
                document_id=document.document_id,
                source_uri=discovered.relative_path,
            )
            status = (
                ManifestStatus.NEEDS_OCR
                if exc.code == IngestionErrorCode.NEEDS_OCR
                else ManifestStatus.FAILED
            )
            self._record_failure(manifest, error, status=status)
            return ParseOutcome(discovered, document, (), error)
        except ValueError as exc:
            error = IngestionError(
                code=IngestionErrorCode.UNSUPPORTED_DOCUMENT,
                message=str(exc),
                document_id=document.document_id,
                source_uri=discovered.relative_path,
            )
            self._record_failure(manifest, error, status=ManifestStatus.FAILED)
            return ParseOutcome(discovered, document, (), error)
        except Exception as exc:
            error = IngestionError(
                code=IngestionErrorCode.UNKNOWN,
                message=f"unexpected parser failure: {exc}",
                document_id=document.document_id,
                source_uri=discovered.relative_path,
            )
            self._record_failure(manifest, error, status=ManifestStatus.FAILED)
            return ParseOutcome(discovered, document, (), error)

    def _record_failure(
        self,
        manifest: ManifestEntry,
        error: IngestionError,
        *,
        status: ManifestStatus,
    ) -> None:
        if self.manifest_store is not None:
            self.manifest_store.upsert(update_manifest_entry(manifest, status=status, error=error))
