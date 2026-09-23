from __future__ import annotations

import math
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pydantic import Field, model_validator

from app.domain.contracts import EvidenceContext, EvidenceSource, SearchHit
from app.domain.models import DomainModel


class TokenCounter(Protocol):
    """Token counter matching the configured generation/model tokenizer."""

    def count_tokens(self, text: str) -> int: ...


class ContextBuildStatus(StrEnum):
    BUILT = "built"
    UNBUILDABLE = "unbuildable"


class OmissionReason(StrEnum):
    DUPLICATE = "duplicate"
    DOCUMENT_LIMIT = "document_limit"
    TOKEN_BUDGET = "token_budget"


class ContextFailureCode(StrEnum):
    NO_EVIDENCE = "no_evidence"
    SOURCE_EXCEEDS_BUDGET = "source_exceeds_budget"
    TOKEN_COUNTER_FAILURE = "token_counter_failure"


class OmittedEvidence(DomainModel):
    chunk_id: str
    reason: OmissionReason


class ContextBuildFailure(DomainModel):
    code: ContextFailureCode
    message: str


class ContextBuildResult(DomainModel):
    status: ContextBuildStatus
    context: EvidenceContext | None = None
    token_count: int = Field(default=0, ge=0)
    omitted: tuple[OmittedEvidence, ...] = ()
    failure: ContextBuildFailure | None = None

    @model_validator(mode="after")
    def validate_result(self) -> ContextBuildResult:
        if (self.status == ContextBuildStatus.BUILT) != (
            self.context is not None and self.failure is None
        ):
            raise ValueError("built context requires context and no failure")
        if (self.status == ContextBuildStatus.UNBUILDABLE) != (self.failure is not None):
            raise ValueError("unbuildable context requires a typed failure")
        if self.status == ContextBuildStatus.UNBUILDABLE and self.context is not None:
            raise ValueError("unbuildable context cannot contain a partial context")
        return self


@dataclass(frozen=True)
class ContextBuilderConfig:
    max_context_tokens: int
    max_chunks_per_document: int = 2

    def __post_init__(self) -> None:
        if self.max_context_tokens < 1:
            raise ValueError("max_context_tokens must be positive")
        if self.max_chunks_per_document < 1:
            raise ValueError("max_chunks_per_document must be positive")


class ContextBuilder:
    """Build stable source-tagged context while respecting dedup, diversity, and budget."""

    def __init__(self, token_counter: TokenCounter, config: ContextBuilderConfig) -> None:
        self._token_counter = token_counter
        self._config = config

    def build(self, query: str, hits: Sequence[SearchHit]) -> ContextBuildResult:
        if not hits:
            return self._unbuildable(ContextFailureCode.NO_EVIDENCE, "no search hits supplied")

        unique: list[SearchHit] = []
        omitted: list[OmittedEvidence] = []
        seen: set[tuple[str, str, str, str]] = set()
        for hit in sorted(hits, key=lambda item: (item.rank, item.chunk_id)):
            key = (
                hit.document_id,
                hit.document_version,
                self._normalize_evidence(hit.text),
                hit.source_location.model_dump_json(),
            )
            if key in seen:
                omitted.append(
                    OmittedEvidence(chunk_id=hit.chunk_id, reason=OmissionReason.DUPLICATE)
                )
                continue
            seen.add(key)
            unique.append(hit)

        eligible: list[SearchHit] = []
        per_document: dict[str, int] = {}
        for hit in unique:
            count = per_document.get(hit.document_id, 0)
            if count >= self._config.max_chunks_per_document:
                omitted.append(
                    OmittedEvidence(chunk_id=hit.chunk_id, reason=OmissionReason.DOCUMENT_LIMIT)
                )
                continue
            per_document[hit.document_id] = count + 1
            eligible.append(hit)

        selected: list[EvidenceSource] = []
        rendered = ""
        token_count = 0
        for hit in eligible:
            source = self._source(hit, len(selected) + 1)
            candidate = (*selected, source)
            candidate_text = self._render(candidate)
            try:
                candidate_tokens = self._token_counter.count_tokens(candidate_text)
            except Exception:
                return self._unbuildable(
                    ContextFailureCode.TOKEN_COUNTER_FAILURE,
                    "token counter failed while building evidence context",
                    omitted=omitted,
                )
            if not isinstance(candidate_tokens, int) or candidate_tokens < 0:
                return self._unbuildable(
                    ContextFailureCode.TOKEN_COUNTER_FAILURE,
                    "token counter returned an invalid token count",
                    omitted=omitted,
                )
            if candidate_tokens > self._config.max_context_tokens:
                omitted.append(
                    OmittedEvidence(chunk_id=hit.chunk_id, reason=OmissionReason.TOKEN_BUDGET)
                )
                continue
            selected.append(source)
            rendered = candidate_text
            token_count = candidate_tokens

        if not selected:
            return self._unbuildable(
                ContextFailureCode.SOURCE_EXCEEDS_BUDGET,
                "no complete evidence source fits the configured context budget",
                omitted=omitted,
            )
        return ContextBuildResult(
            status=ContextBuildStatus.BUILT,
            context=EvidenceContext(query=query, rendered_text=rendered, sources=tuple(selected)),
            token_count=token_count,
            omitted=tuple(omitted),
        )

    @staticmethod
    def _source(hit: SearchHit, index: int) -> EvidenceSource:
        return EvidenceSource(
            source_id=f"S{index}",
            chunk_id=hit.chunk_id,
            document_id=hit.document_id,
            document_version=hit.document_version,
            title=hit.title,
            source_uri=hit.source_uri,
            source_location=hit.source_location,
            text=hit.text,
        )

    @staticmethod
    def _render(sources: Sequence[EvidenceSource]) -> str:
        blocks = []
        for source in sources:
            location = source.source_location
            location_parts = []
            if location.page_start is not None:
                page_range = str(location.page_start)
                if location.page_end != location.page_start:
                    page_range += f"-{location.page_end}"
                location_parts.append(f"page {page_range}")
            if location.section_path:
                location_parts.append("section " + " > ".join(location.section_path))
            if location.paragraph_start is not None:
                paragraph_range = str(location.paragraph_start)
                if location.paragraph_end != location.paragraph_start:
                    paragraph_range += f"-{location.paragraph_end}"
                location_parts.append(f"paragraph {paragraph_range}")
            if location.line_start is not None:
                line_range = str(location.line_start)
                if location.line_end != location.line_start:
                    line_range += f"-{location.line_end}"
                location_parts.append(f"line {line_range}")
            if location.char_start is not None:
                char_range = str(location.char_start)
                if location.char_end != location.char_start:
                    char_range += f"-{location.char_end}"
                location_parts.append(f"characters {char_range}")
            locator = "; ".join(location_parts)
            blocks.append(
                f"[{source.source_id}] {source.title}\n"
                f"document: {source.document_id}@{source.document_version}\n"
                f"source: {source.source_uri}\n"
                f"chunk: {source.chunk_id}\n"
                f"location: {locator}\n"
                f"{source.text}"
            )
        return "\n\n".join(blocks)

    @staticmethod
    def _normalize_evidence(text: str) -> str:
        return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()

    @staticmethod
    def _unbuildable(
        code: ContextFailureCode,
        message: str,
        *,
        omitted: Sequence[OmittedEvidence] = (),
    ) -> ContextBuildResult:
        return ContextBuildResult(
            status=ContextBuildStatus.UNBUILDABLE,
            omitted=tuple(omitted),
            failure=ContextBuildFailure(code=code, message=message),
        )


class EvidenceDecisionStatus(StrEnum):
    SUFFICIENT = "sufficient"
    INSUFFICIENT = "insufficient_evidence"


class EvidenceDecisionReason(StrEnum):
    SUFFICIENT_SCORE = "sufficient_score"
    NO_HITS = "no_hits"
    SCORE_BELOW_THRESHOLD = "score_below_threshold"
    TOO_FEW_DOCUMENTS = "too_few_documents"


class EvidenceDecision(DomainModel):
    status: EvidenceDecisionStatus
    reason: EvidenceDecisionReason
    best_score: float | None = None
    minimum_score: float = 0.0
    document_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_scores(self) -> EvidenceDecision:
        for value in (self.best_score, self.minimum_score):
            if value is not None and not math.isfinite(value):
                raise ValueError("evidence scores must be finite")
        return self


@dataclass(frozen=True)
class EvidenceGateConfig:
    minimum_score: float = 0.0
    minimum_documents: int = 1

    def __post_init__(self) -> None:
        if not math.isfinite(self.minimum_score) or not -1.0 <= self.minimum_score <= 1.0:
            raise ValueError("minimum_score must be between -1 and 1")
        if self.minimum_documents < 1:
            raise ValueError("minimum_documents must be positive")


class EvidenceGate:
    """Deterministic score/source sufficiency check; it never invokes a provider."""

    def __init__(self, config: EvidenceGateConfig | None = None) -> None:
        self._config = config or EvidenceGateConfig()

    def evaluate(self, hits: Sequence[SearchHit]) -> EvidenceDecision:
        if not hits:
            return EvidenceDecision(
                status=EvidenceDecisionStatus.INSUFFICIENT,
                reason=EvidenceDecisionReason.NO_HITS,
                minimum_score=self._config.minimum_score,
            )
        best_score = max(hit.score for hit in hits)
        document_count = len({hit.document_id for hit in hits})
        if best_score < self._config.minimum_score:
            return EvidenceDecision(
                status=EvidenceDecisionStatus.INSUFFICIENT,
                reason=EvidenceDecisionReason.SCORE_BELOW_THRESHOLD,
                best_score=best_score,
                minimum_score=self._config.minimum_score,
                document_count=document_count,
            )
        if document_count < self._config.minimum_documents:
            return EvidenceDecision(
                status=EvidenceDecisionStatus.INSUFFICIENT,
                reason=EvidenceDecisionReason.TOO_FEW_DOCUMENTS,
                best_score=best_score,
                minimum_score=self._config.minimum_score,
                document_count=document_count,
            )
        return EvidenceDecision(
            status=EvidenceDecisionStatus.SUFFICIENT,
            reason=EvidenceDecisionReason.SUFFICIENT_SCORE,
            best_score=best_score,
            minimum_score=self._config.minimum_score,
            document_count=document_count,
        )
