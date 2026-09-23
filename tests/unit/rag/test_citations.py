from __future__ import annotations

from app.domain.contracts import Citation, Claim, EvidenceContext, EvidenceSource
from app.domain.models import SourceLocation
from app.rag.citations import CitationIssueCode, CitationValidator


def _context() -> EvidenceContext:
    source = EvidenceSource(
        source_id="S1",
        chunk_id="chunk-1",
        document_id="doc-1",
        document_version="v1",
        title="Synthetic guide",
        source_uri="samples/guide.md",
        source_location=SourceLocation(
            page_start=2,
            page_end=2,
            section_path=("Retention",),
        ),
        text="Records are retained for seven years, unless law requires longer retention.",
    )
    return EvidenceContext(
        query="How long are records retained?",
        rendered_text="[S1] " + source.text,
        sources=(source,),
    )


def _citation(*, quote: str | None = "seven years") -> Citation:
    return Citation(
        citation_id="C1",
        source_id="S1",
        chunk_id="chunk-1",
        document_id="doc-1",
        document_version="v1",
        title="Synthetic guide",
        source_uri="samples/guide.md",
        source_location=SourceLocation(
            page_start=2,
            page_end=2,
            section_path=("Retention",),
        ),
        quote=quote,
    )


def test_citation_validator_accepts_grounded_claim_and_normalized_quote() -> None:
    result = CitationValidator().validate(
        (Claim(text="Records are retained for seven years.", citation_ids=("C1",)),),
        (_citation(quote="  seven   years "),),
        _context(),
    )

    assert result.valid
    assert result.issues == ()


def test_citation_validator_rejects_uncited_claim_unknown_id_and_quote() -> None:
    result = CitationValidator().validate(
        (
            Claim(text="This factual claim has no citation."),
            Claim(text="Unknown source reference.", citation_ids=("C9",)),
            Claim(text="Unsupported quote.", citation_ids=("C1",)),
        ),
        (_citation(quote="records are retained for 90 years"),),
        _context(),
    )

    assert not result.valid
    assert [issue.code for issue in result.issues] == [
        CitationIssueCode.UNSUPPORTED_QUOTE,
        CitationIssueCode.UNCITED_CLAIM,
        CitationIssueCode.UNKNOWN_CITATION,
    ]


def test_citation_validator_rejects_unknown_sources_and_forged_identity() -> None:
    context = _context()
    unknown_source = _citation().model_copy(update={"source_id": "S9"})
    forged = _citation().model_copy(update={"document_version": "v2"})

    unknown_result = CitationValidator().validate(
        (Claim(text="Claim.", citation_ids=("C1",)),),
        (unknown_source,),
        context,
    )
    assert not unknown_result.valid
    assert unknown_result.issues[0].code == CitationIssueCode.UNKNOWN_SOURCE

    forged_result = CitationValidator().validate(
        (Claim(text="Claim.", citation_ids=("C1",)),),
        (forged,),
        context,
    )
    assert not forged_result.valid
    assert forged_result.issues[0].code == CitationIssueCode.SOURCE_IDENTITY_MISMATCH


def test_citation_validator_rejects_duplicate_citation_ids() -> None:
    citation = _citation()
    result = CitationValidator().validate(
        (Claim(text="Claim.", citation_ids=("C1",)),),
        (citation, citation),
        _context(),
    )

    assert not result.valid
    assert result.issues[0].code == CitationIssueCode.DUPLICATE_CITATION_ID
