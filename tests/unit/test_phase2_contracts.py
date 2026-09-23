from __future__ import annotations

import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.domain.contracts import (
    AnswerStatus,
    Citation,
    Claim,
    EvidenceContext,
    EvidenceSource,
    Failure,
    FailureCode,
    GeneratedAnswer,
    GenerationRequest,
    ProviderOutcomeStatus,
    QueryResponse,
    SearchHit,
    SearchRequest,
    SearchStatus,
    UsageMetrics,
)
from app.domain.fakes import FakeLLMProvider, FakeSearchService

REQUEST_ID = "request-001"


def _location() -> dict[str, object]:
    return {"page_start": 2, "page_end": 2, "section_path": ["Overview"]}


def _hit(*, rank: int = 1, score: float = 0.91) -> SearchHit:
    return SearchHit(
        rank=rank,
        score=score,
        chunk_id="chunk-001",
        document_id="doc-001",
        document_version="v1",
        title="Synthetic guide",
        source_uri="samples/guide.md",
        source_location=_location(),
        text="The service retains records for seven years.",
    )


def _citation() -> Citation:
    return Citation(
        citation_id="C1",
        source_id="S1",
        chunk_id="chunk-001",
        document_id="doc-001",
        document_version="v1",
        title="Synthetic guide",
        source_uri="samples/guide.md",
        source_location=_location(),
        quote="The service retains records for seven years.",
    )


def _generation_request() -> GenerationRequest:
    source = EvidenceSource(
        source_id="S1",
        chunk_id="chunk-001",
        document_id="doc-001",
        document_version="v1",
        title="Synthetic guide",
        source_uri="samples/guide.md",
        source_location=_location(),
        text="The service retains records for seven years.",
    )
    return GenerationRequest(
        query="How long are records retained?",
        context=EvidenceContext(
            query="How long are records retained?",
            rendered_text="[S1] The service retains records for seven years.",
            sources=(source,),
        ),
        request_id=REQUEST_ID,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"query": "   "},
        {"query": "test", "top_k": 0},
        {"query": "test", "top_k": 101},
        {"query": "test", "filters": {"document_type": "unknown"}},
        {"query": "test", "filters": {"industry": ["finance", "  "]}},
        {"query": "test", "filters": {"tenant_id": "other"}},
        {"query": "test", "filters": {"active": False}},
        {"query": "test", "filters": {"unknown": "value"}},
    ],
)
def test_search_request_rejects_invalid_query_k_enum_and_filters(payload) -> None:
    with pytest.raises(ValidationError) as error:
        SearchRequest.model_validate(payload)

    assert error.value.errors()


def test_search_filters_are_normalized_and_serializable() -> None:
    request = SearchRequest(
        query="  retention policy  ",
        top_k=8,
        filters={
            "industry": [" finance ", "finance"],
            "document_type": "product_guide",
            "products": ["Agent X"],
            "document_id": "doc-001",
            "document_version": "v2",
        },
    )

    assert request.query == "retention policy"
    assert request.filters.industry == ("finance",)
    assert request.model_dump(mode="json")["filters"] == {
        "industry": ["finance"],
        "document_type": "product_guide",
        "products": ["Agent X"],
        "document_id": "doc-001",
        "document_version": "v2",
    }


def test_search_hit_serializes_rank_score_identity_and_source_location() -> None:
    hit = _hit()
    payload = hit.model_dump(mode="json")

    assert payload["rank"] == 1
    assert payload["score"] == pytest.approx(0.91)
    assert payload["chunk_id"] == "chunk-001"
    assert payload["document_id"] == "doc-001"
    assert payload["document_version"] == "v1"
    assert payload["source_location"]["page_start"] == 2
    assert payload["source_location"]["section_path"] == ["Overview"]


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "status": "answered",
                "request_id": REQUEST_ID,
                "answer": "Records are retained for seven years.",
                "claims": [
                    {"text": "Records are retained for seven years.", "citation_ids": ["C1"]}
                ],
                "citations": [_citation().model_dump(mode="json")],
                "warnings": ["synthetic"],
                "metrics": {"input_tokens": 12, "output_tokens": 8, "total_tokens": 20},
                "trace": {"request_id": REQUEST_ID, "latency_ms": 4.5},
            },
            AnswerStatus.ANSWERED,
        ),
        (
            {
                "status": "insufficient_evidence",
                "request_id": REQUEST_ID,
                "warnings": ["No matching evidence."],
            },
            AnswerStatus.INSUFFICIENT_EVIDENCE,
        ),
        (
            {
                "status": "failed",
                "request_id": REQUEST_ID,
                "failure": {
                    "code": "retrieval_unavailable",
                    "message": "Search is unavailable.",
                    "retryable": True,
                },
            },
            AnswerStatus.FAILED,
        ),
    ],
)
def test_query_response_serializes_each_terminal_status(payload, expected) -> None:
    response = QueryResponse.model_validate(payload)

    assert response.status == expected
    assert response.model_dump(mode="json")["request_id"] == REQUEST_ID


def test_query_response_rejects_inconsistent_status_and_usage() -> None:
    with pytest.raises(ValidationError):
        QueryResponse(status="answered", request_id=REQUEST_ID)
    with pytest.raises(ValidationError):
        QueryResponse(
            status="failed",
            request_id=REQUEST_ID,
            failure=Failure(code=FailureCode.PROVIDER_FAILURE, message="failed"),
            answer="must not be returned",
        )
    with pytest.raises(ValidationError):
        UsageMetrics(input_tokens=1, output_tokens=2, total_tokens=8)


def test_contract_import_succeeds_when_infrastructure_and_provider_sdks_are_blocked() -> None:
    code = """
import importlib.abc
import sys

blocked = ("fastapi", "qdrant_client", "openai", "langchain", "langgraph")

class BlockImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + ".") for name in blocked):
            raise AssertionError("forbidden SDK import: " + fullname)
        return None

sys.meta_path.insert(0, BlockImports())
from app.domain.contracts import SearchRequest, QueryResponse, LLMProvider
from app.domain.fakes import FakeSearchService, FakeLLMProvider
assert SearchRequest(query="ok")
assert LLMProvider
assert FakeSearchService and FakeLLMProvider and QueryResponse
"""

    check = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert check.returncode == 0, check.stderr


def test_fake_search_supports_success_empty_and_failure_deterministically() -> None:
    request = SearchRequest(query="retention", top_k=1)
    success = FakeSearchService(hits=(_hit(),))
    first = success.search(request, request_id=REQUEST_ID)
    second = success.search(request, request_id=REQUEST_ID)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.status == SearchStatus.SUCCEEDED
    assert first.hits[0].rank == 1
    assert FakeSearchService().search(request, request_id=REQUEST_ID).status == SearchStatus.EMPTY

    failed = FakeSearchService(
        failure=Failure(
            code=FailureCode.RETRIEVAL_UNAVAILABLE,
            message="vector store unavailable",
            retryable=True,
        )
    ).search(request, request_id=REQUEST_ID)
    assert failed.status == SearchStatus.FAILED
    assert failed.failure is not None
    assert failed.failure.code == FailureCode.RETRIEVAL_UNAVAILABLE


@pytest.mark.parametrize("kind", ["success", "malformed", "failure"])
def test_fake_llm_supports_all_provider_paths(kind) -> None:
    request = _generation_request()
    if kind == "success":
        fake = FakeLLMProvider(
            answer=GeneratedAnswer(
                answer="Records are retained for seven years.",
                claims=(Claim(text="Records are retained for seven years.", citation_ids=("C1",)),),
                citations=(_citation(),),
                usage=UsageMetrics(input_tokens=10, output_tokens=7, total_tokens=17),
            )
        )
        result = fake.generate(request)
        assert result.status == ProviderOutcomeStatus.SUCCEEDED
        assert result.answer is not None
        assert result.answer.answer == "Records are retained for seven years."
    elif kind == "malformed":
        fake = FakeLLMProvider(malformed_output={"answer": 42})
        result = fake.generate(request)
        assert result.status == ProviderOutcomeStatus.MALFORMED
        assert result.failure is not None
        assert result.failure.code == FailureCode.MALFORMED_PROVIDER_OUTPUT
    else:
        fake = FakeLLMProvider(
            failure=Failure(
                code=FailureCode.PROVIDER_TIMEOUT, message="provider timed out", retryable=True
            )
        )
        result = fake.generate(request)
        assert result.status == ProviderOutcomeStatus.FAILED
        assert result.failure is not None
        assert result.failure.code == FailureCode.PROVIDER_TIMEOUT

    assert fake.requests == [request]
