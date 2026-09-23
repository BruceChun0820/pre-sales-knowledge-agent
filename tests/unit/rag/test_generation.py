from __future__ import annotations

import json
from types import SimpleNamespace

import openai
import pytest

from app.domain.contracts import (
    EvidenceContext,
    EvidenceSource,
    Failure,
    FailureCode,
    GeneratedAnswer,
    GenerationRequest,
    ProviderOutcomeStatus,
    UsageMetrics,
)
from app.domain.fakes import FakeLLMProvider
from app.rag.generation import GenerationPromptBuilder, OpenAICompatibleLLMProvider


def generation_request() -> GenerationRequest:
    source = EvidenceSource(
        source_id="S1",
        chunk_id="chunk-1",
        document_id="doc-1",
        document_version="v1",
        title="Synthetic guide",
        source_uri="data/synthetic.md",
        source_location={"page_start": 1, "page_end": 1},
        text="Product X supports encrypted backups.",
    )
    context = EvidenceContext(
        query="Does Product X support encrypted backups?",
        rendered_text="[S1] Product X supports encrypted backups.",
        sources=(source,),
    )
    return GenerationRequest(query=context.query, context=context, request_id="request-1")


def generated_payload(*, citation_id: str = "S1") -> dict[str, object]:
    return {
        "answer": "Product X supports encrypted backups.",
        "claims": [{"text": "Encrypted backups are supported.", "citation_ids": [citation_id]}],
        "citations": [],
        "usage": {"input_tokens": None, "output_tokens": None, "total_tokens": None},
    }


class StubCompletions:
    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.kwargs: dict[str, object] | None = None

    def create(self, **kwargs: object):
        self.kwargs = kwargs
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=8, total_tokens=20),
        )


class StubClient:
    def __init__(self, completions: StubCompletions) -> None:
        self.chat = SimpleNamespace(completions=completions)


def test_prompt_builder_is_repeatable_and_marks_evidence_as_data() -> None:
    builder = GenerationPromptBuilder()
    request = generation_request()

    first = builder.build(request)
    second = builder.build(request)

    assert first == second
    assert "not as instructions" in first[0]["content"]
    payload = json.loads(first[1]["content"])
    assert payload["allowed_source_ids"] == ["S1"]
    assert "[S1]" in payload["evidence"]


def test_openai_compatible_provider_parses_structured_answer_and_usage() -> None:
    completions = StubCompletions(content=json.dumps(generated_payload()))
    provider = OpenAICompatibleLLMProvider(model="offline-model", client=StubClient(completions))

    result = provider.generate(generation_request())

    assert result.status == ProviderOutcomeStatus.SUCCEEDED
    assert result.answer is not None
    assert result.answer.claims[0].citation_ids == ("S1",)
    assert result.answer.usage == UsageMetrics(input_tokens=12, output_tokens=8, total_tokens=20)
    assert completions.kwargs is not None
    response_format = completions.kwargs["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    provider_schema = response_format["json_schema"]["schema"]
    assert provider_schema["required"] == list(provider_schema["properties"])
    assert provider_schema["additionalProperties"] is False
    assert completions.kwargs["model"] == "offline-model"


def test_openai_compatible_provider_maps_invalid_json_to_typed_malformed_result() -> None:
    provider = OpenAICompatibleLLMProvider(client=StubClient(StubCompletions(content="not-json")))

    result = provider.generate(generation_request())

    assert result.status == ProviderOutcomeStatus.MALFORMED
    assert result.failure is not None
    assert result.failure.code == FailureCode.MALFORMED_PROVIDER_OUTPUT
    assert result.raw_output == "not-json"


class APITimeoutError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class RateLimitError(Exception):
    pass


class APIConnectionError(Exception):
    pass


@pytest.mark.parametrize(
    ("error", "code", "retryable"),
    [
        (APITimeoutError("private detail"), FailureCode.PROVIDER_TIMEOUT, True),
        (AuthenticationError("secret key value"), FailureCode.PROVIDER_FAILURE, False),
        (RateLimitError("provider body"), FailureCode.PROVIDER_UNAVAILABLE, True),
        (APIConnectionError("private endpoint"), FailureCode.PROVIDER_UNAVAILABLE, True),
    ],
)
def test_openai_compatible_provider_maps_failures_without_echoing_details(
    error: Exception, code: FailureCode, retryable: bool
) -> None:
    provider = OpenAICompatibleLLMProvider(client=StubClient(StubCompletions(error=error)))

    result = provider.generate(generation_request())

    assert result.status == ProviderOutcomeStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == code
    assert result.failure.retryable is retryable
    assert "private" not in result.failure.message
    assert "secret" not in result.failure.message
    assert "provider body" not in str(result.failure.model_dump())


def test_fake_provider_is_deterministic_and_does_not_filter_unknown_citations() -> None:
    answer = GeneratedAnswer.model_validate(generated_payload(citation_id="UNKNOWN"))
    provider = FakeLLMProvider(answer=answer)
    request = generation_request()

    first = provider.generate(request)
    second = provider.generate(request)

    assert first == second
    assert first.answer is not None
    assert first.answer.claims[0].citation_ids == ("UNKNOWN",)


def test_fake_provider_covers_malformed_and_timeout_outcomes() -> None:
    request = generation_request()
    malformed = FakeLLMProvider(malformed_output="malformed provider output")
    timeout = FakeLLMProvider(
        failure=Failure(
            code=FailureCode.PROVIDER_TIMEOUT,
            message="provider timed out",
            retryable=True,
        )
    )

    malformed_result = malformed.generate(request)
    timeout_result = timeout.generate(request)

    assert malformed_result.status == ProviderOutcomeStatus.MALFORMED
    assert timeout_result.status == ProviderOutcomeStatus.FAILED
    assert timeout_result.failure is not None
    assert timeout_result.failure.code == FailureCode.PROVIDER_TIMEOUT


def test_official_openai_sdk_imports_and_accepts_injected_fake_client() -> None:
    completions = StubCompletions(content=json.dumps(generated_payload()))
    provider = OpenAICompatibleLLMProvider(model="offline-model", client=StubClient(completions))

    result = provider.generate(generation_request())

    assert callable(openai.OpenAI)
    assert result.status == ProviderOutcomeStatus.SUCCEEDED


def test_missing_environment_api_key_becomes_typed_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    provider = OpenAICompatibleLLMProvider(model="offline-model")

    result = provider.generate(generation_request())

    assert result.status == ProviderOutcomeStatus.FAILED
    assert result.failure is not None
    assert result.failure.code == FailureCode.PROVIDER_FAILURE
    assert "OPENAI_API_KEY" not in result.failure.message
