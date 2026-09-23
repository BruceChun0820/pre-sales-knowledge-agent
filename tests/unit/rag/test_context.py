from __future__ import annotations

from app.domain.contracts import SearchHit
from app.domain.models import SourceLocation
from app.rag.context import (
    ContextBuilder,
    ContextBuilderConfig,
    ContextBuildStatus,
    ContextFailureCode,
    EvidenceDecisionReason,
    EvidenceDecisionStatus,
    EvidenceGate,
    EvidenceGateConfig,
    OmissionReason,
)


class WordCounter:
    def count_tokens(self, text: str) -> int:
        return len(text.split())


def _hit(
    chunk_id: str,
    *,
    rank: int,
    text: str,
    document_id: str = "doc-1",
    page: int = 1,
) -> SearchHit:
    return SearchHit(
        rank=rank,
        score=0.9 - rank / 100,
        chunk_id=chunk_id,
        document_id=document_id,
        document_version="v1",
        title=f"Guide {document_id}",
        source_uri=f"samples/{document_id}.md",
        source_location=SourceLocation(page_start=page, page_end=page, section_path=("Limits",)),
        text=text,
    )


def test_context_builder_is_deterministic_deduplicates_and_diversifies() -> None:
    counter = WordCounter()
    hits = (
        _hit("c1", rank=1, text="Value is 42 percent."),
        _hit("c1-copy", rank=2, text="Value is 42 percent."),
        _hit("c2", rank=3, text="A second chunk from this guide."),
        _hit(
            "c3",
            rank=4,
            text="An independent guide confirms the requirement.",
            document_id="doc-2",
            page=3,
        ),
    )
    builder = ContextBuilder(
        counter,
        ContextBuilderConfig(max_context_tokens=1000, max_chunks_per_document=1),
    )

    first = builder.build("What is the limit?", hits)
    second = builder.build("What is the limit?", hits)

    assert first.status == ContextBuildStatus.BUILT
    assert first.context is not None
    assert second.context is not None
    assert first.context.model_dump(mode="json") == second.context.model_dump(mode="json")
    assert [source.source_id for source in first.context.sources] == ["S1", "S2"]
    assert [source.chunk_id for source in first.context.sources] == ["c1", "c3"]
    assert [(item.chunk_id, item.reason) for item in first.omitted] == [
        ("c1-copy", OmissionReason.DUPLICATE),
        ("c2", OmissionReason.DOCUMENT_LIMIT),
    ]
    assert first.context.rendered_text.startswith("[S1]")
    assert "[S2]" in first.context.rendered_text
    assert first.token_count <= 1000


def test_context_builder_respects_exact_budget_and_returns_typed_overflow() -> None:
    counter = WordCounter()
    hits = (
        _hit("c1", rank=1, text="First source is bounded."),
        _hit("c2", rank=2, text="Second source remains optional.", document_id="doc-2"),
    )
    full = ContextBuilder(counter, ContextBuilderConfig(max_context_tokens=1000)).build(
        "query", hits
    )
    assert full.status == ContextBuildStatus.BUILT
    assert full.context is not None

    limited = ContextBuilder(
        counter,
        ContextBuilderConfig(max_context_tokens=full.token_count - 1),
    ).build("query", hits)
    assert limited.status == ContextBuildStatus.BUILT
    assert limited.context is not None
    assert len(limited.context.sources) == 1
    assert limited.token_count <= full.token_count - 1
    assert limited.omitted[0].reason == OmissionReason.TOKEN_BUDGET

    impossible = ContextBuilder(counter, ContextBuilderConfig(max_context_tokens=1)).build(
        "query", hits[:1]
    )
    assert impossible.status == ContextBuildStatus.UNBUILDABLE
    assert impossible.context is None
    assert impossible.failure is not None
    assert impossible.failure.code == ContextFailureCode.SOURCE_EXCEEDS_BUDGET


def test_context_builder_handles_empty_evidence_and_token_counter_failure() -> None:
    builder = ContextBuilder(WordCounter(), ContextBuilderConfig(max_context_tokens=100))
    empty = builder.build("query", ())
    assert empty.status == ContextBuildStatus.UNBUILDABLE
    assert empty.failure is not None
    assert empty.failure.code == ContextFailureCode.NO_EVIDENCE

    class BrokenCounter:
        def count_tokens(self, text: str) -> int:
            raise RuntimeError("private tokenizer error")

    broken = ContextBuilder(BrokenCounter(), ContextBuilderConfig(max_context_tokens=100)).build(
        "query", (_hit("c1", rank=1, text="Evidence."),)
    )
    assert broken.status == ContextBuildStatus.UNBUILDABLE
    assert broken.failure is not None
    assert broken.failure.code == ContextFailureCode.TOKEN_COUNTER_FAILURE
    assert "private" not in broken.failure.message


def test_evidence_gate_applies_configurable_score_and_source_criteria() -> None:
    low_hits = (_hit("c1", rank=1, text="Low relevance.").model_copy(update={"score": 0.2}),)
    low = EvidenceGate(EvidenceGateConfig(minimum_score=0.6)).evaluate(low_hits)
    assert low.status == EvidenceDecisionStatus.INSUFFICIENT
    assert low.reason == EvidenceDecisionReason.SCORE_BELOW_THRESHOLD

    two_sources = (
        _hit("c1", rank=1, text="Evidence one.").model_copy(update={"score": 0.7}),
        _hit("c2", rank=2, text="Evidence two.", document_id="doc-2").model_copy(
            update={"score": 0.65}
        ),
    )
    sufficient = EvidenceGate(EvidenceGateConfig(minimum_score=0.6, minimum_documents=2)).evaluate(
        two_sources
    )
    assert sufficient.status == EvidenceDecisionStatus.SUFFICIENT
    assert sufficient.reason == EvidenceDecisionReason.SUFFICIENT_SCORE

    no_hits = EvidenceGate().evaluate(())
    assert no_hits.status == EvidenceDecisionStatus.INSUFFICIENT
    assert no_hits.reason == EvidenceDecisionReason.NO_HITS


def test_context_builder_keeps_repeated_text_when_source_location_differs() -> None:
    result = ContextBuilder(
        WordCounter(),
        ContextBuilderConfig(max_context_tokens=1000, max_chunks_per_document=5),
    ).build(
        "query",
        (
            _hit("c1", rank=1, text="The same wording appears.", page=1),
            _hit("c2", rank=2, text="The same wording appears.", page=2),
        ),
    )

    assert result.context is not None
    assert [source.chunk_id for source in result.context.sources] == ["c1", "c2"]
    assert [source.source_location.page_start for source in result.context.sources] == [1, 2]
