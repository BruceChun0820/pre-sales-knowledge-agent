# P2-TASK-04 — Structured Answer Generation Handoff

## Delivery

- Branch: feature/phase-02-dev2-generation-api
- Base: 268c6674771984d2b844195f291263ae265b342d
- Head: recorded in the implementation PR after commit.
- PR: recorded after push; target main.

## Scope and Files

- app/rag/generation.py: deterministic evidence-only prompt builder and OpenAI-compatible structured-output adapter. The adapter uses the official SDK, strict JSON Schema mode, typed parsing, usage extraction, and stable timeout/authentication/rate-limit/unavailable/provider-failure mapping. API credentials are read through the SDK environment configuration.
- app/domain/fakes.py: existing frozen deterministic provider fake reused without contract edits.
- tests/unit/rag/test_generation.py: fake and injected-client coverage for deterministic success, malformed output, unknown citation passthrough, timeout, authentication, rate limit, provider unavailability, schema mode, and usage mapping.
- pyproject.toml, requirements-phase2.lock: approved FastAPI, Uvicorn, and official OpenAI client dependency declarations and exact environment lock.

## Acceptance Evidence

- AC-P2-09: deterministic offline fake covers success, malformed output, timeout, and provider failure; adapter tests use an injected fake client and make no network calls.
- AC-P2-10: provider secrets are supplied by SDK environment configuration; failure messages do not echo provider exception text; API log redaction coverage is in P2-TASK-05.
- Citation rejection remains the responsibility of the frozen downstream citation validator and P2-TASK-07 integration.

## Verification

- Focused: .venv/bin/python -m pytest tests/unit/rag/test_generation.py tests/unit/api/test_api.py tests/integration/api/test_api_integration.py -q — 23 passed.
- Full: ./init.sh — 96 passed; Ruff lint, format, and whitespace/conflict checks passed.
- Clean environment: new temporary Python 3.14 venv installed from requirements-phase2.lock; pip freeze exactly matched the lock; FastAPI, OpenAI, and Uvicorn imports passed.
- Tests are offline by default. No API key or real provider was used.

## Reproduction

From the repository root on the supported Ubuntu/Python 3.14 environment:

    python3 -m venv .venv
    .venv/bin/python -m pip install -r requirements-phase2.lock
    ./init.sh

For a real adapter, set OPENAI_API_KEY; set OPENAI_BASE_URL for an OpenAI-compatible endpoint and OPENAI_MODEL to select the model. Default tests inject an offline fake client.

## Limitations and Next Action

- No real-provider smoke test was run; provider schema interoperability depends on the target endpoint supporting strict JSON Schema structured output.
- Generated citations are parsed but not independently validated in this task; the frozen citation validator owns that check.
- Next: review the combined Dev2 implementation PR; do not start P2-TASK-07 until its documented merge prerequisites are accepted.
