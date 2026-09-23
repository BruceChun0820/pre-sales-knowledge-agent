from __future__ import annotations

from collections.abc import Sequence

from .contracts import (
    Failure,
    FailureCode,
    GeneratedAnswer,
    GenerationRequest,
    LLMProvider,
    ProviderOutcomeStatus,
    ProviderResult,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SearchService,
    SearchStatus,
    TraceMetadata,
)


class FakeSearchService(SearchService):
    """Configurable deterministic search double; it performs no retrieval."""

    def __init__(
        self,
        *,
        hits: Sequence[SearchHit] = (),
        failure: Failure | None = None,
    ) -> None:
        if hits and failure is not None:
            raise ValueError("fake search cannot be configured with hits and failure")
        self._hits = tuple(hits)
        self._failure = failure
        self.requests: list[tuple[SearchRequest, str]] = []

    def search(self, request: SearchRequest, *, request_id: str) -> SearchResponse:
        self.requests.append((request, request_id))
        trace = TraceMetadata(request_id=request_id)
        if self._failure is not None:
            return SearchResponse(status=SearchStatus.FAILED, trace=trace, failure=self._failure)
        hits = self._hits[: request.top_k]
        if not hits:
            return SearchResponse(status=SearchStatus.EMPTY, trace=trace)
        return SearchResponse(status=SearchStatus.SUCCEEDED, hits=hits, trace=trace)


class FakeLLMProvider(LLMProvider):
    """Deterministic generation double for success, malformed output, and failures."""

    def __init__(
        self,
        *,
        answer: GeneratedAnswer | None = None,
        malformed_output: object | None = None,
        failure: Failure | None = None,
    ) -> None:
        configured = sum(value is not None for value in (answer, malformed_output, failure))
        if configured > 1:
            raise ValueError("configure exactly one fake provider outcome")
        self._answer = answer
        self._malformed_output = malformed_output
        self._failure = failure
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> ProviderResult:
        self.requests.append(request)
        if self._failure is not None:
            return ProviderResult(status=ProviderOutcomeStatus.FAILED, failure=self._failure)
        if self._malformed_output is not None:
            return ProviderResult(
                status=ProviderOutcomeStatus.MALFORMED,
                raw_output=self._malformed_output,
                failure=Failure(
                    code=FailureCode.MALFORMED_PROVIDER_OUTPUT,
                    message="fake provider output is malformed",
                ),
            )
        answer = self._answer or GeneratedAnswer(answer="Deterministic fake answer.")
        return ProviderResult(status=ProviderOutcomeStatus.SUCCEEDED, answer=answer)
