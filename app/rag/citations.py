from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from enum import StrEnum

from app.domain.contracts import Citation, Claim, EvidenceContext, EvidenceSource
from app.domain.models import DomainModel


class CitationIssueCode(StrEnum):
    UNCITED_CLAIM = "uncited_claim"
    UNKNOWN_CITATION = "unknown_citation"
    DUPLICATE_CITATION_ID = "duplicate_citation_id"
    UNKNOWN_SOURCE = "unknown_source"
    SOURCE_IDENTITY_MISMATCH = "source_identity_mismatch"
    UNSUPPORTED_QUOTE = "unsupported_quote"


class CitationIssue(DomainModel):
    code: CitationIssueCode
    message: str
    claim_index: int | None = None
    citation_id: str | None = None


class CitationValidationResult(DomainModel):
    valid: bool
    issues: tuple[CitationIssue, ...] = ()


class CitationValidator:
    """Validate citation identity, claim coverage, and quote grounding deterministically."""

    def validate(
        self,
        claims: Sequence[Claim],
        citations: Sequence[Citation],
        context: EvidenceContext,
    ) -> CitationValidationResult:
        issues: list[CitationIssue] = []
        source_by_id = {source.source_id: source for source in context.sources}
        citation_by_id: dict[str, Citation] = {}
        invalid_citation_ids: set[str] = set()

        for citation in citations:
            if citation.citation_id in citation_by_id:
                issues.append(
                    CitationIssue(
                        code=CitationIssueCode.DUPLICATE_CITATION_ID,
                        citation_id=citation.citation_id,
                        message="citation ID appears more than once",
                    )
                )
                invalid_citation_ids.add(citation.citation_id)
                continue
            citation_by_id[citation.citation_id] = citation
            source = source_by_id.get(citation.source_id)
            if source is None:
                issues.append(
                    CitationIssue(
                        code=CitationIssueCode.UNKNOWN_SOURCE,
                        citation_id=citation.citation_id,
                        message="citation source ID is absent from supplied evidence",
                    )
                )
                invalid_citation_ids.add(citation.citation_id)
                continue
            if not self._matches_source(citation, source):
                issues.append(
                    CitationIssue(
                        code=CitationIssueCode.SOURCE_IDENTITY_MISMATCH,
                        citation_id=citation.citation_id,
                        message="citation identity does not match its supplied source",
                    )
                )
                invalid_citation_ids.add(citation.citation_id)
            if citation.quote is not None and not self._contains_quote(source.text, citation.quote):
                issues.append(
                    CitationIssue(
                        code=CitationIssueCode.UNSUPPORTED_QUOTE,
                        citation_id=citation.citation_id,
                        message="citation quote is not grounded in supplied evidence",
                    )
                )
                invalid_citation_ids.add(citation.citation_id)

        for index, claim in enumerate(claims):
            if not claim.citation_ids:
                issues.append(
                    CitationIssue(
                        code=CitationIssueCode.UNCITED_CLAIM,
                        claim_index=index,
                        message="claim has no citation",
                    )
                )
                continue
            for citation_id in claim.citation_ids:
                if citation_id not in citation_by_id:
                    issues.append(
                        CitationIssue(
                            code=CitationIssueCode.UNKNOWN_CITATION,
                            claim_index=index,
                            citation_id=citation_id,
                            message="claim references an unknown citation ID",
                        )
                    )
                elif citation_id in invalid_citation_ids:
                    # The source-level issue already explains why this citation is invalid.
                    continue

        return CitationValidationResult(valid=not issues, issues=tuple(issues))

    @staticmethod
    def _matches_source(citation: Citation, source: EvidenceSource) -> bool:
        return (
            citation.chunk_id == source.chunk_id
            and citation.document_id == source.document_id
            and citation.document_version == source.document_version
            and citation.title == source.title
            and citation.source_uri == source.source_uri
            and citation.source_location == source.source_location
        )

    @staticmethod
    def _contains_quote(evidence: str, quote: str) -> bool:
        normalized_evidence = CitationValidator._normalize(evidence)
        normalized_quote = CitationValidator._normalize(quote)
        return bool(normalized_quote) and normalized_quote in normalized_evidence

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()
