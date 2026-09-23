from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

DEFAULT_TENANT_ID = "demo"
DOCUMENT_VERSION_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
SHA256_PATTERN = r"^[0-9a-fA-F]{64}$"

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
DocumentVersion = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=128,
        pattern=DOCUMENT_VERSION_PATTERN,
    ),
]
Sha256Checksum = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=64, max_length=64, pattern=SHA256_PATTERN),
]
TenantId = Literal[DEFAULT_TENANT_ID]
MetadataValue = str | int | float | bool | None


class DocumentType(StrEnum):
    PRODUCT_GUIDE = "product_guide"
    SOLUTION = "solution"
    CASE_STUDY = "case_study"
    PROPOSAL = "proposal"
    RFP = "rfp"
    IMPLEMENTATION_GUIDE = "implementation_guide"
    OTHER = "other"


class Language(StrEnum):
    ZH = "zh"
    EN = "en"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class Confidentiality(StrEnum):
    PUBLIC = "public"
    SYNTHETIC = "synthetic"


class DocumentStatus(StrEnum):
    DISCOVERED = "discovered"
    PARSED = "parsed"
    CHUNKED = "chunked"
    INDEXED = "indexed"
    ACTIVE = "active"
    SKIPPED = "skipped"
    FAILED = "failed"
    NEEDS_OCR = "needs_ocr"


class BlockType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"
    CAPTION = "caption"


class IngestionErrorCode(StrEnum):
    INVALID_INPUT = "invalid_input"
    UNSUPPORTED_DOCUMENT = "unsupported_document"
    PARSE_FAILED = "parse_failed"
    VALIDATION_FAILED = "validation_failed"
    EMBEDDING_FAILED = "embedding_failed"
    VECTOR_STORE_FAILED = "vector_store_failed"
    NEEDS_OCR = "needs_ocr"
    UNKNOWN = "unknown"


class IngestionResultStatus(StrEnum):
    SUCCEEDED = "succeeded"
    SKIPPED = "skipped"
    PARTIAL = "partial"
    FAILED = "failed"


class DomainModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _normalize_labels(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, (list, tuple, set, frozenset)):
        raise ValueError("labels must be a sequence of strings")

    labels: list[str] = []
    for label in value:
        if not isinstance(label, str):
            raise ValueError("labels must contain only strings")
        cleaned = label.strip()
        if not cleaned:
            raise ValueError("labels must not contain empty values")
        if cleaned not in labels:
            labels.append(cleaned)
    return tuple(labels)


class SourceLocation(DomainModel):
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section_path: tuple[NonEmptyString, ...] = ()
    paragraph_start: int | None = Field(default=None, ge=0)
    paragraph_end: int | None = Field(default=None, ge=0)
    line_start: int | None = Field(default=None, ge=0)
    line_end: int | None = Field(default=None, ge=0)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)

    @field_validator("section_path", mode="before")
    @classmethod
    def normalize_section_path(cls, value: object) -> tuple[str, ...]:
        return _normalize_labels(value)

    @model_validator(mode="after")
    def validate_ranges_and_identity(self) -> SourceLocation:
        for start_name, end_name in (
            ("page_start", "page_end"),
            ("paragraph_start", "paragraph_end"),
            ("line_start", "line_end"),
            ("char_start", "char_end"),
        ):
            start = getattr(self, start_name)
            end = getattr(self, end_name)
            if (start is None) != (end is None):
                raise ValueError(f"{start_name} and {end_name} must be provided together")
            if start is not None and end is not None and end < start:
                raise ValueError(f"{end_name} must not be less than {start_name}")

        has_stable_locator = any(
            value is not None
            for value in (
                self.page_start,
                self.paragraph_start,
                self.line_start,
                self.char_start,
            )
        ) or bool(self.section_path)
        if not has_stable_locator:
            raise ValueError(
                "source location requires a page, section, paragraph, line, or character locator"
            )
        return self


class DocumentRecord(DomainModel):
    tenant_id: TenantId = DEFAULT_TENANT_ID
    document_id: NonEmptyString
    document_version: DocumentVersion
    title: NonEmptyString
    source_uri: NonEmptyString
    document_type: DocumentType
    industry: tuple[NonEmptyString, ...] = ()
    products: tuple[NonEmptyString, ...] = ()
    language: Language = Language.UNKNOWN
    published_at: date | None = None
    active: bool = False
    confidentiality: Confidentiality
    content_checksum: Sha256Checksum
    status: DocumentStatus = DocumentStatus.DISCOVERED
    parser_name: NonEmptyString | None = None
    parser_version: NonEmptyString | None = None
    metadata: Mapping[str, MetadataValue] = Field(default_factory=dict)

    @field_validator("industry", "products", mode="before")
    @classmethod
    def normalize_metadata_labels(cls, value: object) -> tuple[str, ...]:
        return _normalize_labels(value)


class ParsedBlock(DomainModel):
    document_id: NonEmptyString
    document_version: DocumentVersion
    block_id: NonEmptyString
    block_type: BlockType
    text: NonEmptyString
    source_location: SourceLocation
    order: int = Field(ge=0)
    parser_name: NonEmptyString
    parser_version: NonEmptyString
    section_path: tuple[NonEmptyString, ...] = ()

    @field_validator("section_path", mode="before")
    @classmethod
    def normalize_section_path(cls, value: object) -> tuple[str, ...]:
        return _normalize_labels(value)


class Chunk(DomainModel):
    tenant_id: TenantId = DEFAULT_TENANT_ID
    document_id: NonEmptyString
    document_version: DocumentVersion
    chunk_id: NonEmptyString
    text: NonEmptyString
    text_checksum: Sha256Checksum
    source_location: SourceLocation
    title: NonEmptyString
    source_uri: NonEmptyString
    document_type: DocumentType
    industry: tuple[NonEmptyString, ...] = ()
    products: tuple[NonEmptyString, ...] = ()
    language: Language = Language.UNKNOWN
    published_at: date | None = None
    active: bool = False
    confidentiality: Confidentiality
    section_path: tuple[NonEmptyString, ...] = ()
    chunk_index: int = Field(ge=0)
    parser_version: NonEmptyString
    cleaner_version: NonEmptyString
    chunker_version: NonEmptyString
    embedding_model: NonEmptyString | None = None
    embedding_dimension: int | None = Field(default=None, ge=1)
    content_checksum: Sha256Checksum

    @field_validator("industry", "products", "section_path", mode="before")
    @classmethod
    def normalize_metadata_labels(cls, value: object) -> tuple[str, ...]:
        return _normalize_labels(value)

    @model_validator(mode="after")
    def validate_embedding_metadata(self) -> Chunk:
        if (self.embedding_model is None) != (self.embedding_dimension is None):
            raise ValueError("embedding_model and embedding_dimension must be provided together")
        return self


class EmbeddingBatch(DomainModel):
    model_name: NonEmptyString
    model_revision: NonEmptyString
    dimension: int = Field(ge=1)
    chunk_ids: tuple[NonEmptyString, ...] = Field(min_length=1)
    vectors: tuple[tuple[float, ...], ...] = Field(min_length=1)
    normalized: bool = False
    device: NonEmptyString = "cpu"
    dtype: NonEmptyString = "float32"

    @model_validator(mode="after")
    def validate_vectors(self) -> EmbeddingBatch:
        if len(self.chunk_ids) != len(self.vectors):
            raise ValueError("chunk_ids and vectors must have the same length")
        for vector in self.vectors:
            if len(vector) != self.dimension:
                raise ValueError("every vector must match the declared dimension")
            if not all(math.isfinite(value) for value in vector):
                raise ValueError("vectors must contain only finite numbers")
        return self


class IngestionError(DomainModel):
    code: IngestionErrorCode
    message: NonEmptyString
    document_id: NonEmptyString | None = None
    source_uri: NonEmptyString | None = None
    retryable: bool = False
    details: Mapping[str, MetadataValue] = Field(default_factory=dict)


class IngestionResult(DomainModel):
    document_id: NonEmptyString
    document_version: DocumentVersion
    status: IngestionResultStatus
    discovered_blocks: int = Field(default=0, ge=0)
    created_chunks: int = Field(default=0, ge=0)
    embedded_chunks: int = Field(default=0, ge=0)
    upserted_chunks: int = Field(default=0, ge=0)
    errors: tuple[IngestionError, ...] = ()

    @model_validator(mode="after")
    def validate_status_and_errors(self) -> IngestionResult:
        if self.status == IngestionResultStatus.SUCCEEDED and self.errors:
            raise ValueError("a succeeded ingestion result cannot contain errors")
        if (
            self.status in (IngestionResultStatus.PARTIAL, IngestionResultStatus.FAILED)
            and not self.errors
        ):
            raise ValueError("partial or failed ingestion results require at least one error")
        return self
