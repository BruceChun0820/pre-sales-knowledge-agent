from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.domain.contracts import (
    AnswerStatus,
    Claim,
    Failure,
    FailureCode,
    QueryResponse,
    SearchHit,
    SearchRequest,
    UsageMetrics,
)
from app.domain.fakes import FakeSearchService


def hit() -> SearchHit:
    return SearchHit(
        rank=1,
        score=0.9,
        chunk_id="chunk-1",
        document_id="doc-1",
        document_version="v1",
        title="Synthetic guide",
        source_uri="data/synthetic.md",
        source_location={"page_start": 1, "page_end": 1},
        text="Synthetic source text.",
    )


class StubQueryService:
    def __init__(self, response: QueryResponse | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.calls: list[tuple[SearchRequest, str]] = []

    def query(self, request: SearchRequest, *, request_id: str) -> QueryResponse:
        self.calls.append((request, request_id))
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


def client_for(*, search=None, query=None, readiness=None) -> TestClient:
    search = search or FakeSearchService(hits=(hit(),))
    query = query or StubQueryService(
        QueryResponse(
            status=AnswerStatus.ANSWERED,
            request_id="service-request",
            answer="Synthetic answer.",
            claims=(Claim(text="One supported claim.", citation_ids=("S1",)),),
            metrics=UsageMetrics(input_tokens=4, output_tokens=3, total_tokens=7),
        )
    )
    return TestClient(
        create_app(search_service=search, query_service=query, readiness_probe=readiness)
    )


def test_health_distinguishes_liveness_from_dependency_readiness() -> None:
    ready = client_for(readiness=lambda: {"qdrant": True, "llm": True})
    unavailable = client_for(readiness=lambda: {"qdrant": False, "llm": True})

    live_response = ready.get("/v1/health")
    unavailable_response = unavailable.get("/v1/health")

    assert live_response.status_code == 200
    assert live_response.json()["live"] is True
    assert live_response.json()["ready"] is True
    assert live_response.json()["dependencies"] == {"qdrant": True, "llm": True}
    assert live_response.json()["request_id"] == live_response.headers["X-Request-ID"]
    assert unavailable_response.status_code == 503
    assert unavailable_response.json()["live"] is True
    assert unavailable_response.json()["ready"] is False


def test_search_returns_ordered_contract_response_and_request_telemetry() -> None:
    search = FakeSearchService(hits=(hit(),))
    with client_for(search=search) as client:
        response = client.post("/v1/search", json={"query": "synthetic question", "top_k": 3})

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "succeeded"
    assert body["hits"][0]["rank"] == 1
    assert body["trace"]["request_id"] == response.headers["X-Request-ID"]
    assert float(response.headers["X-Latency-Ms"]) >= 0
    assert search.requests[0][1] == response.headers["X-Request-ID"]


def test_search_validation_error_is_stable_and_does_not_echo_rejected_values() -> None:
    client = client_for()

    response = client.post(
        "/v1/search",
        json={"query": "DO-NOT-RETURN-THIS", "top_k": 0},
    )

    body = response.json()
    assert response.status_code == 422
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["failure"]["code"] == "validation_error"
    assert "DO-NOT-RETURN-THIS" not in response.text
    assert "input" not in body["failure"]


def test_search_dependency_failure_is_non_2xx_with_typed_error() -> None:
    search = FakeSearchService(
        failure=Failure(
            code=FailureCode.RETRIEVAL_UNAVAILABLE,
            message="retrieval is unavailable",
            retryable=True,
        )
    )
    client = client_for(search=search)

    response = client.post("/v1/search", json={"query": "question"})

    assert response.status_code == 503
    assert response.json()["failure"]["code"] == "retrieval_unavailable"
    assert response.json()["trace"]["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        (AnswerStatus.ANSWERED, 200),
        (AnswerStatus.INSUFFICIENT_EVIDENCE, 200),
        (AnswerStatus.FAILED, 504),
    ],
)
def test_query_exposes_all_statuses_with_stable_http_mapping(
    status: AnswerStatus, expected_code: int
) -> None:
    failure = (
        Failure(
            code=FailureCode.PROVIDER_TIMEOUT,
            message="generation timed out",
            retryable=True,
        )
        if status == AnswerStatus.FAILED
        else None
    )
    response_model = QueryResponse(
        status=status,
        request_id="service-request",
        answer="Synthetic answer." if status == AnswerStatus.ANSWERED else None,
        claims=(Claim(text="Supported claim.", citation_ids=("S1",)),)
        if status == AnswerStatus.ANSWERED
        else (),
        failure=failure,
    )
    service = StubQueryService(response=response_model)
    client = client_for(query=service)

    response = client.post("/v1/query", json={"query": "question"})

    assert response.status_code == expected_code
    body = response.json()
    assert body["status"] == status.value
    assert body["request_id"] == response.headers["X-Request-ID"]
    assert body["trace"]["request_id"] == body["request_id"]
    assert service.calls[0][1] == body["request_id"]


def test_query_logs_usage_without_question_or_answer_text(caplog: pytest.LogCaptureFixture) -> None:
    query = StubQueryService(
        response=QueryResponse(
            status=AnswerStatus.ANSWERED,
            request_id="service-request",
            answer="PRIVATE-ANSWER-BODY",
            metrics=UsageMetrics(input_tokens=11, output_tokens=7, total_tokens=18),
        )
    )
    client = client_for(query=query)
    caplog.set_level(logging.INFO, logger="app.api")

    response = client.post("/v1/query", json={"query": "PRIVATE-QUESTION-BODY"})

    assert response.status_code == 200
    record = next(record for record in caplog.records if record.message == "api_request_completed")
    assert record.request_id == response.headers["X-Request-ID"]
    assert record.input_tokens == 11
    assert record.output_tokens == 7
    assert record.total_tokens == 18
    assert record.retrieval_top_k == 5
    assert "PRIVATE-QUESTION-BODY" not in caplog.text
    assert "PRIVATE-ANSWER-BODY" not in caplog.text


def test_query_service_exception_returns_sanitized_non_2xx_failure() -> None:
    client = client_for(query=StubQueryService(error=RuntimeError("secret response body")))

    response = client.post("/v1/query", json={"query": "question"})

    assert response.status_code == 503
    assert response.json()["status"] == "failed"
    assert response.json()["failure"]["code"] == "provider_unavailable"
    assert "secret response body" not in response.text


def test_health_is_not_ready_when_no_dependency_probe_is_configured() -> None:
    client = client_for()

    response = client.get("/v1/health")

    assert response.status_code == 503
    assert response.json()["live"] is True
    assert response.json()["ready"] is False
    assert response.json()["dependencies"] == {"readiness_probe_configured": False}


def test_openapi_documents_stable_success_and_error_schemas() -> None:
    client = client_for()

    schema = client.get("/openapi.json").json()

    assert "200" in schema["paths"]["/v1/health"]["get"]["responses"]
    assert "503" in schema["paths"]["/v1/health"]["get"]["responses"]
    assert "422" in schema["paths"]["/v1/search"]["post"]["responses"]
    assert "503" in schema["paths"]["/v1/search"]["post"]["responses"]
    assert "422" in schema["paths"]["/v1/query"]["post"]["responses"]
    assert "504" in schema["paths"]["/v1/query"]["post"]["responses"]
