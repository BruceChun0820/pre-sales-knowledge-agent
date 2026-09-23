# Phase 02 — Basic RAG Q&A + Citation

## Status and Entry Gate

`PLANNED — READY FOR EXPLICIT ACTIVATION`.

Phase 1 is QA PASSED and PM ACCEPTED. Its complete state is promoted to `main`. No Phase 2 production implementation begins until PM/user explicitly declares Phase 2 active. At activation, the promoted Phase 1 `main` SHA is the common checkout baseline for Dev1 and Dev2.

## Objective

Build a minimal direct RAG service that retrieves evidence from the Phase 1 Qdrant index, returns source-aware search results, and produces structured answers whose factual claims are traceable to validated citations.

This phase answers: **Can the system answer or explicitly refuse a question using only indexed evidence, through stable APIs and reproducible tests?**

## Scope

- Typed query, search, answer, claim, citation, error, trace, and usage contracts.
- Deterministic query normalization that preserves identifiers, numbers, and negation.
- Dense retrieval using the Phase 1 embedding model and Qdrant adapter.
- Explicit metadata filters with zero scope leakage.
- Deterministic context construction with deduplication, source diversity, stable source IDs, and configurable budget.
- Evidence-sufficiency decision before generation.
- OpenAI-compatible LLM adapter behind a provider-neutral interface.
- Deterministic fake LLM for tests; no external service is required by CI.
- Structured answer generation and deterministic citation validation.
- Explicit `insufficient_evidence` behavior; retrieval/LLM failures must not produce an answer.
- FastAPI endpoints: `/v1/health`, `/v1/search`, and `/v1/query`.
- Request ID, latency, selected retrieval settings, and token/usage telemetry without logging document bodies or secrets.
- Reproducible retrieval and answer/citation baseline reports.

## Out of Scope

- Agent loop, LangGraph, Tool Calling, ReAct, Planning, Reflection, memory, Human-in-the-loop, or Multi-Agent.
- Query rewrite, reranking, sparse vectors, hybrid retrieval, or automatic filter inference.
- Proposal generation, multi-document comparison, workflow tools, UI, authentication/SSO, multi-tenant authorization, or production deployment.
- Re-ingestion redesign, parser/chunker changes, OCR, table extraction improvements, or embedding-model reselection.
- Streaming responses, chat history, persistent conversation state, web search, arbitrary file/network access, or CRM integration.
- Java, Kafka, Redis, Kubernetes, microservices, or unrelated services.

Any request requiring these items returns to PM as a scope change.

## Architecture Impact

Phase 2 extends the modular monolith while preserving a direct, framework-light RAG path:

```text
HTTP request
  -> FastAPI schema/validation
  -> DirectRAGService
       -> QueryProcessor
       -> DenseRetriever -> EmbeddingProvider + VectorStore
       -> ContextBuilder -> EvidenceGate
       -> AnswerGenerator -> LLMProvider
       -> CitationValidator
  -> typed QueryResponse
```

The API layer may depend on application/domain contracts. Domain contracts must not import FastAPI, Qdrant, or an LLM SDK. The LLM adapter is replaceable; the deterministic fake is the default test boundary. The direct RAG service remains callable without HTTP so future Agent tools can reuse it.

## Technical Decisions

### TD-P2-01 — Direct RAG before Agent orchestration

1. **Problem:** Citation and retrieval defects must be testable without Agent decisions.
2. **Options:** introduce LangGraph now; implement a direct service first.
3. **Decision:** implement `Question -> Retrieve -> Evidence Gate -> Generate -> Validate` as plain typed services.
4. **Reason:** deterministic boundaries make quality and failures measurable.
5. **Trade-off:** Phase 4 will add orchestration wrappers later, while the direct path remains supported.

### TD-P2-02 — Contract-first parallelization

1. **Problem:** Dev1 retrieval output and Dev2 generation/API input share public schemas.
2. **Options:** let each stream invent schemas; freeze a small shared contract first.
3. **Decision:** `P2-TASK-01` is a gating PR. After merge, public Phase 2 contracts are frozen for Wave 1.
4. **Reason:** prevents incompatible parallel implementations and repeated merge conflicts.
5. **Trade-off:** parallel work starts after one small serial gate rather than immediately.

### TD-P2-03 — OpenAI-compatible adapter plus deterministic fake

1. **Problem:** production-like generation is needed, but tests cannot depend on credentials, network, or nondeterministic output.
2. **Options:** call one SDK directly; use a provider-neutral interface with real/fake adapters.
3. **Decision:** define an `LLMProvider` contract, one OpenAI-compatible adapter, and a deterministic fake.
4. **Reason:** provider behavior, error mapping, schema parsing, and citation checks can be tested independently.
5. **Trade-off:** a small adapter layer is maintained; provider-specific features remain deferred.

### TD-P2-04 — Citation validation outside the LLM

1. **Problem:** an LLM can invent source IDs or unsupported quotations.
2. **Options:** trust prompt compliance; deterministically validate generated citations.
3. **Decision:** assign stable source IDs before generation and reject unknown IDs, missing claim citations, and quotes not grounded in supplied evidence.
4. **Reason:** citation integrity becomes a testable invariant.
5. **Trade-off:** some otherwise plausible answers are rejected; safety takes priority over answer rate.

### TD-P2-05 — Dense retrieval baseline only

1. **Problem:** retrieval improvements cannot be attributed if several techniques are added together.
2. **Options:** add rewrite/rerank/hybrid now; establish a dense baseline first.
3. **Decision:** use dense retrieval plus explicit user-supplied metadata filters only.
4. **Reason:** Phase 3 experiments need a reproducible baseline.
5. **Trade-off:** known hard queries may underperform until Phase 3.

### TD-P2-06 — Minimal Phase 2 runtime dependencies

1. **Problem:** The service needs an HTTP boundary, ASGI runtime, and OpenAI-compatible client without pulling in a general Agent framework.
2. **Options:** FastAPI plus official OpenAI client; hand-written HTTP calls; LangChain provider wrappers.
3. **Decision:** Dev2 may add and lock only `fastapi`, `uvicorn`, and the official `openai` Python client, plus a direct test dependency only if not already available. All provider use remains behind `LLMProvider`.
4. **Reason:** This matches the approved stack, keeps the adapter small, supports configurable OpenAI-compatible base URLs, and avoids LangChain coupling.
5. **Trade-off:** The official client is an additional dependency and provider quirks still require adapter tests. A direct `httpx` implementation remains the fallback if a documented Python compatibility spike fails.

## Parallel Execution Plan

```text
Phase 1 QA PASSED + PM ACCEPTED + promoted to main
              |
PM declares Phase 2 ACTIVE and dispatches Dev1 + Dev2
              |
Wave 0: Dev1 writes P2-TASK-01 contract PR
        Dev2 performs read-only preparation
              |
      contract PR merged to dev
          /                   \
Wave 1 Dev1                   Wave 1 Dev2
P2-TASK-02 -> 03              P2-TASK-04 -> 05
          \                   /
       reviewed PRs merged to dev
          /                   \
Wave 2 Dev1                   Wave 2 Dev2
P2-TASK-06                    P2-TASK-07 integration
          \                   /
            Independent QA
```

At Phase 2 activation, the coordinator records the accepted `main` SHA and creates both worker branches/worktrees from it. Both workers receive their complete prompts and ownership boundaries. Dev2 remains at a no-write gate until the contract PR is merged. The coordinator then records the merged contract `dev` SHA; both workers must sync that exact gate commit before production edits.

Workers do not edit coordinator-owned shared trackers. Cross-stream integration occurs only after reviewed PRs merge to `dev`; neither worker directly pushes to the shared `dev` branch.

## Phase 2 Activation Protocol

PM must record all of the following before dispatch:

1. Phase 1 QA result, PM acceptance, and completed `dev -> main` promotion.
2. Accepted Phase 1 `main` SHA.
3. Dev1 and Dev2 worker prompts and assigned Task IDs.
4. Exact task branch and worktree for each worker.
5. Owned/shared/forbidden paths and remote PR target.

Dispatch sequence:

1. PM creates the Dev1 and Dev2 task branches/worktrees from the same accepted `main` SHA.
2. Dev1 receives P2-TASK-01 on `feature/phase-02-contracts`; Dev2 receives its full handoff and may inspect/read/prepare a test plan, but makes no repository changes yet.
3. After P2-TASK-01 is reviewed and merged, PM records the contract SHA.
4. PM instructs both implementation streams to sync the exact merged contract `dev` SHA and sends the execution prompts:
   - Dev1: `feature/phase-02-dev1-retrieval-evidence`.
   - Dev2: `feature/phase-02-dev2-generation-api`.
5. Dev1 and Dev2 execute concurrently and submit separate remote PRs to `dev`.
6. PM integrates reviewed PRs, records the resulting `dev` SHA, and dispatches the final integration branch.

## Tasks

### P2-TASK-01 — Freeze Domain/API Contracts and Test Doubles

**Owner:** Dev1 in Wave 0.

**Goal**

Define framework-neutral Phase 2 contracts that allow retrieval and generation/API streams to work independently.

**Input**

- Accepted Phase 1 domain/vector-store interfaces.
- `REQUIREMENTS.md`, `ARCHITECTURE.md`, and `RAG_DESIGN.md`.

**Expected Output**

- Typed models/enums for filters, search request/hit/response, evidence context/source, answer status, claim, citation, query response, trace/usage, and typed failures.
- Provider-neutral `LLMProvider` and any Phase 2 service protocols.
- Minimal deterministic fakes/builders needed by both streams.
- Contract serialization and validation tests.

**Technical Constraints**

- Domain contracts import no FastAPI, Qdrant, OpenAI SDK, LangChain, or LangGraph types.
- Contract changes must be backward compatible with accepted Phase 1 types or explicitly escalated.
- No HTTP endpoint, retrieval algorithm, or real LLM call in this task.
- After merge, Wave 1 workers may not change these contracts without PM approval.

**Dependencies**

- Phase 1 QA PASSED and PM ACCEPTED.

**Acceptance Criteria**

- Empty query, invalid top-k, unknown enum, and malformed filters fail with stable typed validation errors.
- Search hits can serialize rank, score, chunk identity, document/version identity, and source location without framework objects.
- Query responses serialize `answered`, `insufficient_evidence`, and `failed` statuses, claims, citations, warnings, metrics, and request ID.
- Contract modules import successfully when FastAPI, Qdrant, and the OpenAI SDK are absent.
- Deterministic fakes support retrieval success/empty/failure and LLM success/malformed/failure paths.

### P2-TASK-02 — Query Processing and Dense Retrieval

**Owner:** Dev1.

**Goal**

Convert a validated search request into deterministic dense retrieval results with explicit filters and provenance.

**Input**

- Frozen Phase 2 contracts.
- Accepted Phase 1 embedding provider and vector-store adapter.

**Expected Output**

- Query processor and dense retriever.
- Search result mapping with score/rank/source metadata.
- Unit and integration tests using fakes and Qdrant test data.

**Technical Constraints**

- Preserve product codes, quoted phrases, numbers, percentages, and negation.
- No query rewrite, reranker, sparse/hybrid retrieval, or inferred metadata filters.
- Mandatory tenant/active/version scope from system context cannot be overridden by request data.

**Dependencies**

- P2-TASK-01.

**Acceptance Criteria**

- Identical query/config/index state returns identical normalized query and ordered hits within documented score tolerance.
- Every hit includes rank, score, chunk ID, document ID/version, title/source path, and available page/section location.
- Every returned hit satisfies every applied filter; scope violation count is zero in positive and negative tests.
- Empty result and vector-store/provider errors return typed outcomes; no generation is triggered.

### P2-TASK-03 — Context, Evidence Gate, and Citation Validator

**Owner:** Dev1.

**Goal**

Build bounded evidence context and enforce deterministic grounding rules before and after generation.

**Input**

- Ordered search hits from P2-TASK-02.
- Frozen answer/citation contracts.

**Expected Output**

- Context builder with stable `[S1]`, `[S2]` source IDs.
- Configurable evidence-sufficiency gate.
- Citation and claim validator.
- Focused unit/property tests for duplication, budget, source IDs, quotes, and refusal.

**Technical Constraints**

- Context order and IDs must be deterministic.
- Deduplicate identical chunks; merge adjacency only when provenance remains unambiguous.
- Do not truncate citation-critical identifiers or silently exceed the configured context budget.
- A quotation must be a normalized substring of the cited evidence; unknown source IDs are invalid.

**Dependencies**

- P2-TASK-02.

**Acceptance Criteria**

- Same hits/config produce byte-equivalent context and source-ID mapping.
- Constructed context stays within the configured budget or returns a typed unbuildable-context outcome.
- Duplicate evidence appears once and source-diversity policy is deterministic.
- Insufficient evidence returns `insufficient_evidence` before LLM invocation.
- Every factual claim in an accepted answer has at least one valid supplied citation.
- Unknown citation IDs, uncited factual claims, and non-grounded quotes are rejected with stable reasons.

### P2-TASK-04 — Structured Answer Generation

**Owner:** Dev2.

**Goal**

Generate provider-neutral structured answers from supplied evidence while supporting deterministic offline tests.

**Input**

- Frozen Phase 2 contracts and evidence/source IDs.
- Approved OpenAI-compatible provider policy.

**Expected Output**

- Prompt/input builder with evidence-only instructions.
- `LLMProvider` implementations: deterministic fake and OpenAI-compatible adapter.
- Structured output parser and typed provider/schema errors.
- Unit/contract tests; real network calls excluded from default tests.
- Approved dependency/lock update for the OpenAI-compatible client, with import and fake-client compatibility evidence.

**Technical Constraints**

- API key only from environment; never log credentials, full prompt, full context, or provider response body.
- Fake adapter must cover valid, malformed, unknown-citation, timeout, and provider-failure cases.
- No Agent framework, tool calling, memory, or provider-specific contract leakage.

**Dependencies**

- P2-TASK-01.

**Acceptance Criteria**

- Deterministic fake produces the same structured result for the same configured input.
- Valid provider output maps to the frozen answer schema; malformed output becomes a typed failure.
- Timeout, authentication, rate-limit, and unavailable outcomes map to stable internal error categories.
- Test suite runs with no network and no API key.
- Logged fields contain request/trace metadata but no secret or document body.

### P2-TASK-05 — FastAPI and Operational Boundary

**Owner:** Dev2.

**Goal**

Expose stable health, search, and query interfaces without coupling HTTP schemas to infrastructure SDKs.

**Input**

- Frozen contracts.
- P2-TASK-04 adapters and service fakes.

**Expected Output**

- FastAPI application factory and `/v1/health`, `/v1/search`, `/v1/query` endpoints.
- Dependency injection for service/provider fakes and real adapters.
- Error-to-HTTP mapping, request IDs, latency and usage telemetry.
- API schema and endpoint tests.
- Approved dependency/lock update for FastAPI and the ASGI runtime, with clean-environment reproduction notes.

**Technical Constraints**

- Health must distinguish process liveness from dependency readiness.
- No document ingestion/write endpoint.
- No document body or secrets in logs/errors.
- HTTP layer contains no retrieval or generation algorithm.

**Dependencies**

- P2-TASK-01 and P2-TASK-04.

**Acceptance Criteria**

- `/v1/health` returns a schema-valid response and reports dependency readiness without exposing credentials.
- `/v1/search` rejects invalid requests and returns ordered, schema-valid hits on success.
- `/v1/query` returns all three statuses through deterministic fakes with stable error mapping.
- Each response carries a request ID; latency and available token/usage fields are recorded.
- Qdrant/LLM timeout or unavailability yields the documented non-2xx/failed response and no unsupported answer.

### P2-TASK-06 — Retrieval Baseline and Regression Evidence

**Owner:** Dev1.

**Goal**

Establish the reproducible Phase 2 dense retrieval baseline used by later optimization experiments.

**Input**

- Reviewed public/synthetic evaluation cases and accepted Phase 1 index.
- P2-TASK-02/03 implementation.

**Expected Output**

- Versioned evaluation dataset/schema for retrieval and unanswerable cases.
- Reproducible command and report for Hit Rate@K, Recall@K, optional MRR, latency, and failure slices.
- Regression tests for deterministic cases.

**Technical Constraints**

- Record corpus/index, embedding revision, chunk config, filter config, code SHA, and K values.
- Targets are calibration evidence, not permission to change requirements or tune on holdout data.
- Do not add rewrite, reranker, or hybrid behavior to improve the baseline.

**Dependencies**

- P2-TASK-02 and P2-TASK-03.

**Acceptance Criteria**

- Report reproduces from one documented command on the frozen dataset.
- Every case contains query, expected source/chunk or explicit unanswerable label, and slice metadata.
- Report includes Hit Rate@5, Recall@10, eligible MRR, latency distribution, and per-case failures.
- A repeat run with unchanged inputs remains within documented deterministic tolerance.

### P2-TASK-07 — Direct RAG Integration and Acceptance Evidence

**Owner:** Dev2 after Dev1 and Dev2 Wave 1 PRs merge.

**Goal**

Wire the direct RAG service end to end and prove answer, refusal, citation, API, and failure behavior.

**Input**

- Merged P2-TASK-02 through P2-TASK-06 outputs.
- Frozen Phase 2 contracts and deterministic fake LLM.

**Expected Output**

- Direct RAG orchestration service.
- Integration/acceptance tests for search, answer, refusal, invalid citations, and dependency failures.
- Reproducible answer/citation baseline report and complete Dev evidence package.

**Technical Constraints**

- Service calls steps explicitly; no Agent/graph runtime.
- Evidence gate runs before generation; citation validator runs before returning `answered`.
- Failed validation cannot be silently converted to an answered response.

**Dependencies**

- P2-TASK-03, P2-TASK-05, and P2-TASK-06 merged to `dev`.

**Acceptance Criteria**

- Answerable cases return schema-valid claims and citations traceable to indexed source metadata.
- Unanswerable cases skip LLM generation and return `insufficient_evidence` with no fabricated claims.
- Injected unknown citation, uncited factual claim, and unsupported quote cannot return `answered`.
- Qdrant or LLM failure returns `failed`, preserves request ID, and returns no factual answer.
- Full API acceptance suite passes offline with the fake provider; an optional real-provider smoke test is separately marked and never required by CI.
- Baseline report records answer correctness review, groundedness/faithfulness, citation precision/coverage/validity, latency, and token usage when available.

## Phase Acceptance Criteria

| ID | PASS condition |
|---|---|
| AC-P2-01 | The remote contract PR targets `dev`, passes checks, is reviewed, and frozen contracts import without FastAPI/Qdrant/LLM SDKs. |
| AC-P2-02 | Search requests reject empty queries, invalid K, and malformed/unauthorized filters with stable errors. |
| AC-P2-03 | Dense search returns ordered rank/score/chunk/source metadata and produces zero metadata-scope violations. |
| AC-P2-04 | Same inputs/config produce deterministic normalized query, context order, and source IDs. |
| AC-P2-05 | Context is deduplicated and budget-bounded; overflow/unbuildable context has a typed outcome. |
| AC-P2-06 | Evidence below the configured criterion skips LLM invocation and returns `insufficient_evidence`. |
| AC-P2-07 | Every factual claim in an `answered` response has at least one valid citation from supplied evidence. |
| AC-P2-08 | Unknown source IDs, unsupported quotations, and uncited factual claims cannot return `answered`. |
| AC-P2-09 | Fake LLM tests run offline and deterministically cover success, malformed, timeout, and failure paths. |
| AC-P2-10 | OpenAI-compatible credentials come only from environment and no logs/errors contain secrets or source bodies. |
| AC-P2-11 | `/v1/health`, `/v1/search`, and `/v1/query` conform to their published schemas and error mappings. |
| AC-P2-12 | Qdrant/LLM unavailability yields `failed`/documented HTTP errors and never an unsupported answer. |
| AC-P2-13 | Responses/traces contain request ID and latency; token usage is captured when the provider supplies it. |
| AC-P2-14 | Retrieval and answer/citation baseline reports reproduce with recorded corpus/index/model/config/code identity. |
| AC-P2-15 | Full format, lint, unit, integration, contract, and acceptance checks exit 0 on the tested remote PR head. |
| AC-P2-16 | No Agent/LangGraph/query rewrite/reranker/hybrid/UI/CRM/private data or other out-of-scope component is introduced. |
| AC-P2-17 | Every implementation is delivered by reachable remote PR(s) targeting `dev`; QA tests exact remote head SHAs and Dev does not self-merge. |

Missing evidence is a FAIL, not “not tested.”

## Quality Gates

Before QA:

- `./init.sh` exits 0 in the documented isolated environment.
- Format, lint, unit, integration, contract, and acceptance tests report zero failures/errors.
- Public interfaces are typed and critical invariants have docstrings/documentation.
- Dependency additions are minimal, locked, justified, and approved by their owning handoff.
- No committed secret, API key, private data, model weights, cache, Qdrant volume, or generated runtime artifact.
- No unapproved cross-stream file ownership violation or contract divergence.
- Every task PR includes Task IDs, AC mapping, commands/results, known limitations, branch/base/head SHA, and rollback/reproduction notes.
- Final integration PR is rebased/merged on the accepted `dev` state and contains no unresolved conflict markers or skipped tests.

## Branch and Worktree Plan

Required branch/worktree separation after Phase 2 activation:

| Stream | Branch | Remote Ubuntu worktree | Base |
|---|---|---|---|
| Contract gate | `feature/phase-02-contracts` | `/home/bruce/Dev/pre-sales-knowledge-agent-phase2-contracts` | accepted Phase 1 `main` SHA |
| Dev1 | `feature/phase-02-dev1-retrieval-evidence` | `/home/bruce/Dev/pre-sales-knowledge-agent-phase2-dev1` | created from accepted `main`; sync merged contract `dev` SHA before writes |
| Dev2 | `feature/phase-02-dev2-generation-api` | `/home/bruce/Dev/pre-sales-knowledge-agent-phase2-dev2` | created from accepted `main`; sync merged contract `dev` SHA before writes |
| Integration | `feature/phase-02-direct-rag-integration` | `/home/bruce/Dev/pre-sales-knowledge-agent-phase2-integration` | `dev` after both Wave 1 PRs merge |

These are task branches, not permanent personal branches. They are archived/deleted after their PR is merged. The coordinator confirms paths are unused before creating worktrees and records the exact accepted `main` and gate `dev` SHAs at dispatch time. Do not reuse or clean an earlier Phase worktree.

Merge order is contract PR, then the two independent Wave 1 PRs after review, then the integration PR. If the second Wave 1 PR conflicts with the first merged PR, its owner rebases/merges the latest `dev`, reruns all checks, and updates the remote PR; the coordinator does not resolve the conflict by copying files between worktrees.

## Phase Exit

Phase 2 exits only after all AC-P2-01 through AC-P2-17 are QA PASS, PM confirms scope/architecture compliance, all approved PRs are merged to `dev`, documentation matches actual behavior, and the accepted `dev` SHA is recorded. Promotion from `dev` to `main` remains a separate PM decision.
