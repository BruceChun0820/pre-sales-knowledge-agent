# Phase 02 Dev2 Handoff — Generation, API, and Integration

## Authorization State

`PLANNED — PM MAY DISPATCH AT PHASE 2 START, BUT REPOSITORY WRITES REMAIN BLOCKED UNTIL P2-TASK-01 IS MERGED AND PM PROVIDES THE CONTRACT SHA`.

## Assigned Tasks

- `P2-TASK-04` — structured answer generation adapters.
- `P2-TASK-05` — FastAPI and operational boundary.
- `P2-TASK-07` — direct RAG integration and acceptance evidence, after Dev1/Dev2 Wave 1 PRs merge.

Authoritative requirements and ACs are in `docs/phases/PHASE-02.md`.

## Required Modules / Owned Paths

Expected ownership:

```text
app/models/                 # HTTP-facing request/response models if needed
app/api/                    # app factory, dependencies, routes, error mapping
app/core/observability.py   # request/latency/usage telemetry only
app/rag/generation.py       # prompt/input, provider adapters, structured parser
app/rag/service.py          # P2-TASK-07 direct orchestration
pyproject.toml              # only pre-approved Phase 2 dependencies
requirements-phase2.lock   # exact Phase 2 environment, naming finalized by PM
tests/unit/api/
tests/unit/rag/test_generation*.py
tests/integration/api/
tests/acceptance/
evaluation/reports/        # answer/citation baseline output policy
docs/handoffs/P2-TASK-*.md
```

Do not modify Dev1-owned retrieval/evidence modules. Dev2 is pre-authorized to add and lock only `fastapi`, `uvicorn`, and the official `openai` client as defined by TD-P2-06. Any other dependency or shared setting requires coordinator approval and belongs in a clearly identified commit.

## Functional Requirements

- Provide deterministic fake and OpenAI-compatible LLM adapters behind the frozen interface.
- Parse structured answer/claim/citation output and map provider failures to stable errors.
- Expose `/v1/health`, `/v1/search`, and `/v1/query` through injected services.
- Record request ID, latency, and available token usage without source text or secrets.
- In integration, enforce retrieve -> evidence gate -> generate -> citation validate.
- Return `answered`, `insufficient_evidence`, or `failed` without unsupported fallback answers.

## Technical Constraints

- One worktree/branch per stream; all PRs target `main`.
- Default tests are offline and require no API key.
- API key is environment-only; no raw prompt/context/provider body in logs/errors.
- HTTP layer contains no retrieval or generation algorithm.
- No public-contract change, retrieval implementation, Agent/LangGraph, streaming, chat memory, UI, or ingestion endpoint.
- Do not edit `AGENTS.md`, `feature_list.json`, `progress.md`, phase docs, Dev1-owned files, or dependency files without explicit approval.

## Delivery Sequence

1. At Phase 2 kickoff, read the complete handoff and inspect the accepted code read-only; record questions to PM without changing repository files.
2. Confirm `feature/phase-02-dev2-generation-api` in `/home/bruce/Dev/pre-sales-knowledge-agent-phase2-dev2` was created from the accepted `main` SHA; after the contract PR merges, sync the coordinator-provided contract `main` SHA before editing.
3. Implement P2-TASK-04 and P2-TASK-05; push a remote PR targeting `main`; stop for review/QA/merge.
4. After Dev1 and Dev2 Wave 1 PRs merge, create `feature/phase-02-direct-rag-integration` in the dedicated integration worktree from the new coordinator-provided SHA.
5. Implement P2-TASK-07, run full checks, push, and open the integration PR; do not merge it.

## Acceptance and Quality Gates

Map evidence to AC-P2-07 through AC-P2-17 as applicable. Show offline fake coverage for success/malformed/timeout/failure, endpoint schema/error tests, secret/log checks, full integration acceptance, and baseline report reproduction. `./init.sh` must exit 0.

## Forbidden Changes

- Retrieval ranking/context/citation-rule ownership changes without Dev1/PM review.
- Agent, tool calling, query rewrite, reranker, hybrid search, UI, CRM, ingestion writes, or unrelated infrastructure.
- Real-provider calls in required CI/default tests.
- Direct push to `main`, self-merge, skipped tests, or weaker ACs.

## Stop and Escalate

Stop with evidence if the frozen contracts cannot express provider/API behavior, a new runtime dependency is required, logs cannot meet data-boundary rules, or integration needs a Dev1-owned change. Include affected Task/AC, options, trade-off, and recommendation.
