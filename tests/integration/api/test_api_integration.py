from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import create_app
from app.domain.contracts import (
    AnswerStatus,
    Failure,
    FailureCode,
    QueryResponse,
    SearchHit,
)
from app.domain.fakes import FakeSearchService


class QueryServiceDouble:
    def __init__(self, response: QueryResponse) -> None:
        self.response = response

    def query(self, request, *, request_id: str) -> QueryResponse:
        return self.response.model_copy(update={"request_id": request_id})


def test_injected_contract_fakes_work_through_http_boundary() -> None:
    search_hit = SearchHit(
        rank=1,
        score=0.8,
        chunk_id="synthetic-chunk",
        document_id="synthetic-document",
        document_version="v1",
        title="Synthetic source",
        source_uri="data/synthetic.md",
        source_location={"section_path": ["Overview"]},
        text="Synthetic evidence only.",
    )
    query_response = QueryResponse(
        status=AnswerStatus.FAILED,
        request_id="placeholder",
        failure=Failure(
            code=FailureCode.PROVIDER_TIMEOUT,
            message="generation provider timed out",
            retryable=True,
        ),
    )
    app = create_app(
        search_service=FakeSearchService(hits=(search_hit,)),
        query_service=QueryServiceDouble(query_response),
        readiness_probe=lambda: {"search": True, "generation": True},
    )

    with TestClient(app) as client:
        search_response = client.post("/v1/search", json={"query": "synthetic evidence"})
        query_result = client.post("/v1/query", json={"query": "synthetic question"})

    assert search_response.status_code == 200
    assert search_response.json()["hits"][0]["chunk_id"] == "synthetic-chunk"
    assert search_response.json()["trace"]["request_id"] == search_response.headers["X-Request-ID"]
    assert query_result.status_code == 504
    assert query_result.json()["status"] == "failed"
    assert query_result.json()["request_id"] == query_result.headers["X-Request-ID"]
    assert query_result.json()["answer"] is None
