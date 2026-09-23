from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from app.domain.models import (
    DocumentVersion,
    DomainModel,
    IngestionError,
    NonEmptyString,
    Sha256Checksum,
)

from .discovery import DiscoveredFile


class ManifestStatus(StrEnum):
    DISCOVERED = "discovered"
    PARSED = "parsed"
    FAILED = "failed"
    CHUNKED = "chunked"
    INDEXED = "indexed"
    ACTIVE = "active"
    SKIPPED = "skipped"
    NEEDS_OCR = "needs_ocr"


class ManifestEntry(DomainModel):
    """Versioned manifest state for one source document."""

    document_id: NonEmptyString
    document_version: DocumentVersion
    source_uri: NonEmptyString
    content_checksum: Sha256Checksum
    status: ManifestStatus
    parser_name: NonEmptyString | None = None
    parser_version: NonEmptyString | None = None
    discovered_at: datetime
    updated_at: datetime
    error: IngestionError | None = None

    @classmethod
    def from_discovered_file(cls, discovered: DiscoveredFile) -> ManifestEntry:
        timestamp = datetime.now(UTC)
        return cls(
            document_id=discovered.document_id,
            document_version=discovered.document_version,
            source_uri=discovered.relative_path,
            content_checksum=discovered.content_checksum,
            status=ManifestStatus.DISCOVERED,
            discovered_at=timestamp,
            updated_at=timestamp,
        )


class ManifestStore:
    """Persist a deterministic JSONL manifest with atomic replacement."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> tuple[ManifestEntry, ...]:
        if not self.path.exists():
            return ()
        entries: list[ManifestEntry] = []
        contents = self.path.read_text(encoding="utf-8")
        for line_number, line in enumerate(contents.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                entries.append(ManifestEntry.model_validate_json(line))
            except ValueError as exc:
                raise ValueError(f"invalid manifest entry at line {line_number}: {exc}") from exc
        return tuple(sorted(entries, key=lambda entry: (entry.document_id, entry.document_version)))

    def get(self, document_id: str, document_version: str | None = None) -> ManifestEntry | None:
        matches = [
            entry
            for entry in self.load()
            if entry.document_id == document_id
            and (document_version is None or entry.document_version == document_version)
        ]
        return max(matches, key=lambda entry: entry.updated_at, default=None)

    def upsert(self, entry: ManifestEntry) -> None:
        entries = {
            (current.document_id, current.document_version): current for current in self.load()
        }
        entries[(entry.document_id, entry.document_version)] = entry
        ordered_lines = [
            current.model_dump_json()
            for _, current in sorted(entries.items(), key=lambda item: item[0])
        ]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary_path.write_text("\n".join(ordered_lines) + "\n", encoding="utf-8")
        temporary_path.replace(self.path)


def update_manifest_entry(
    entry: ManifestEntry,
    *,
    status: ManifestStatus,
    parser_name: str | None = None,
    parser_version: str | None = None,
    error: IngestionError | None = None,
) -> ManifestEntry:
    """Create an immutable manifest update while preserving discovery time."""

    return entry.model_copy(
        update={
            "status": status,
            "parser_name": parser_name if parser_name is not None else entry.parser_name,
            "parser_version": parser_version
            if parser_version is not None
            else entry.parser_version,
            "updated_at": datetime.now(UTC),
            "error": error,
        }
    )
