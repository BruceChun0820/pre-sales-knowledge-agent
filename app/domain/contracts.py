from __future__ import annotations

import math
from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Protocol

from pydantic import Field, StringConstraints, field_validator, model_validator

from .models import Chunk, DocumentType, DomainModel, NonEmptyString, SourceLocation

ContractId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class SearchStatus(StrEnum):
    SUCCEEDED = "succeeded"
    EMPTY = "empty"
    FAILED = "failed"


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    FAILED = "failed"


class FailureCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    RETRIEVAL_UNAVAILABLE = "retrieval_unavailable"
    PROVIDER_TIMEOUT = "provider_timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_FAILURE = "provider_failure"
    MALFORMED_PROVIDER_OUTPUT = "malformed_provider_output"


class ProviderOutcomeStatus(StrEnum):
    SUCCEEDED = "succeeded"
    MALFORMED = "malformed"
    FAILED = "failed"


class SearchFilters(DomainModel):
    """Explicit, user-controlled metadata filters; tenant and active scope are system-owned."""

    industry: tuple[NonEmptyString, ...] = ()
    document_type: DocumentType | None = None
    products: tuple[NonEmptyString, ...] = ()
    document_id: NonEmptyString | None = None
    document_version: NonEmptyString | None = None

    @field_validator("industry", "products", mode="before")
    @classmethod
    def normalize_filter_values(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str) or not isinstance(value, (list, tuple)):
            raise ValueError("filter values must be a string or sequence of strings")
        normalized: list[str] = []
        for item in value:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("filter values must contain non-empty strings")
            item = item.strip()
            if item not in normalized:
                normalized.append(item)
        if not normalized and value:
            raise ValueError("filter values must not be empty")
        return tuple(normalized)


class SearchRequest(DomainModel):
    query: NonEmptyString
    top_k: int = Field(default=5, ge=1, le=100)
    filters: SearchFilters = Field(default_factory=SearchFilters)


class SearchHit(DomainModel):
    rank: int = Field(ge=1)
    score: float
    chunk_id: NonEmptyString
    document_id: NonEmptyString
    document_version: NonEmptyString
    title: NonEmptyString
    source_uri: NonEmptyString
    source_location: SourceLocation
    text: NonEmptyString

    @field_validator("score")
    @classmethod
    def finite_score(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("score must be finite")
        return value

    @classmethod
    def from_chunk(cls, chunk: Chunk, *, rank: int, score: float) -> SearchHit:
        return cls(
            rank=rank,
            score=score,
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            document_version=chunk.document_version,
            title=chunk.title,
            source_uri=chunk.source_uri,
            source_location=chunk.source_location,
            text=chunk.text,
        )


class UsageMetrics(DomainModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_total(self) -> UsageMetrics:
        if (
            self.input_tokens is not None
            and self.output_tokens is not None
            and self.total_tokens is not None
            and self.total_tokens != self.input_tokens + self.output_tokens
        ):
            raise ValueError("total_tokens must equal input_tokens + output_tokens")
        return self


class TraceMetadata(DomainModel):
    request_id: ContractId
    trace_id: ContractId | None = None
    latency_ms: float | None = Field(default=None, ge=0)
    stage_latency_ms: Mapping[NonEmptyString, float] = Field(default_factory=dict)

    @field_validator("latency_ms")
    @classmethod
    def finite_latency(cls, value: float | None) -> float | None:
        if value is not None and not math.isfinite(value):
            raise ValueError("latency_ms must be finite")
        return value


class SearchResponse(DomainModel):
    status: SearchStatus
    hits: tuple[SearchHit, ...] = ()
    trace: TraceMetadata
    warnings: tuple[NonEmptyString, ...] = ()
    failure: Failure | None = None

    @model_validator(mode="after")
    def validate_search_state(self) -> SearchResponse:
        if self.status == SearchStatus.SUCCEEDED and not self.hits:
            raise ValueError("succeeded search response requires at least one hit")
        if self.status == SearchStatus.EMPTY and self.hits:
            raise ValueError("empty search response cannot contain hits")
        if (self.status == SearchStatus.FAILED) != (self.failure is not None):
            raise ValueError("failed search responses require exactly one failure")
        return self


class EvidenceSource(DomainModel):
    source_id: ContractId
    chunk_id: NonEmptyString
    document_id: NonEmptyString
    document_version: NonEmptyString
    title: NonEmptyString
    source_uri: NonEmptyString
    source_location: SourceLocation
    text: NonEmptyString


class EvidenceContext(DomainModel):
    query: NonEmptyString
    rendered_text: NonEmptyString
    sources: tuple[EvidenceSource, ...] = Field(min_length=1)


class Claim(DomainModel):
    text: NonEmptyString
    citation_ids: tuple[ContractId, ...] = ()


class Citation(DomainModel):
    citation_id: ContractId
    source_id: ContractId
    chunk_id: NonEmptyString
    document_id: NonEmptyString
    document_version: NonEmptyString
    title: NonEmptyString
    source_uri: NonEmptyString
    source_location: SourceLocation
    quote: NonEmptyString | None = None


class Failure(DomainModel):
    code: FailureCode
    message: NonEmptyString
    retryable: bool = False
    details: Mapping[str, str | int | float | bool | None] = Field(default_factory=dict)


class QueryResponse(DomainModel):
    status: AnswerStatus
    request_id: ContractId
    answer: NonEmptyString | None = None
    claims: tuple[Claim, ...] = ()
    citations: tuple[Citation, ...] = ()
    warnings: tuple[NonEmptyString, ...] = ()
    metrics: UsageMetrics = Field(default_factory=UsageMetrics)
    trace: TraceMetadata | None = None
    failure: Failure | None = None

    @model_validator(mode="after")
    def validate_answer_state(self) -> QueryResponse:
        if self.trace is not None and self.trace.request_id != self.request_id:
            raise ValueError("trace request_id must match response request_id")
        if self.status == AnswerStatus.ANSWERED and self.answer is None:
            raise ValueError("answered responses require an answer")
        if self.status == AnswerStatus.INSUFFICIENT_EVIDENCE and (
            self.answer is not None or self.claims or self.citations or self.failure is not None
        ):
            raise ValueError(
                "insufficient_evidence responses cannot contain answer data or failure"
            )
        if self.status == AnswerStatus.FAILED and (
            self.failure is None or self.answer is not None or self.claims or self.citations
        ):
            raise ValueError("failed responses require a failure and cannot contain answer data")
        if self.status != AnswerStatus.FAILED and self.failure is not None:
            raise ValueError("only failed responses may contain a failure")
        return self


class GenerationRequest(DomainModel):
    query: NonEmptyString
    context: EvidenceContext
    request_id: ContractId


class GeneratedAnswer(DomainModel):
    answer: NonEmptyString
    claims: tuple[Claim, ...] = ()
    citations: tuple[Citation, ...] = ()
    usage: UsageMetrics = Field(default_factory=UsageMetrics)


class ProviderResult(DomainModel):
    status: ProviderOutcomeStatus
    answer: GeneratedAnswer | None = None
    failure: Failure | None = None
    raw_output: (
        Mapping[str, str | int | float | bool | None]
        | list[str | int | float | bool | None]
        | str
        | None
    ) = None

    @model_validator(mode="after")
    def validate_provider_result(self) -> ProviderResult:
        if self.status == ProviderOutcomeStatus.SUCCEEDED and (
            self.answer is None or self.failure is not None or self.raw_output is not None
        ):
            raise ValueError("successful provider results require only a parsed answer")
        if self.status == ProviderOutcomeStatus.MALFORMED and (
            self.raw_output is None
            or self.answer is not None
            or self.failure is None
            or self.failure.code != FailureCode.MALFORMED_PROVIDER_OUTPUT
        ):
            raise ValueError("malformed provider results require raw output and typed failure")
        if self.status == ProviderOutcomeStatus.FAILED and (
            self.failure is None or self.answer is not None or self.raw_output is not None
        ):
            raise ValueError("failed provider results require only a typed failure")
        return self


class SearchService(Protocol):
    """Application boundary for source-aware search; implementation owns retrieval behavior."""

    def search(self, request: SearchRequest, *, request_id: str) -> SearchResponse:
        """Return ranked hits, an empty result, or a typed failure."""


class LLMProvider(Protocol):
    """Provider-neutral boundary for structured generation from supplied evidence."""

    def generate(self, request: GenerationRequest) -> ProviderResult:
        """Return a parsed answer or an explicit malformed/provider failure outcome."""


class QueryService(Protocol):
    """Framework-neutral direct query service boundary for API and offline callers."""

    def query(self, request: SearchRequest, *, request_id: str) -> QueryResponse:
        """Answer, refuse for insufficient evidence, or return a typed failure."""
