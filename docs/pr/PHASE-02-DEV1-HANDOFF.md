# Phase 02 Dev1 Handoff — Retrieval and Evidence

## Authorization State

`PLANNED — DO NOT IMPLEMENT UNTIL PM PROVIDES THE ACCEPTED PHASE 1 DEV SHA`.

## Assigned Tasks

- `P2-TASK-01` — freeze Phase 2 contracts and test doubles (Wave 0, separate gating PR).
- `P2-TASK-02` — deterministic query processing and dense retrieval.
- `P2-TASK-03` — context builder, evidence gate, and citation validator.
- `P2-TASK-06` — retrieval baseline and regression evidence.

Authoritative requirements and ACs are in `docs/phases/PHASE-02.md`.

## Required Modules / Owned Paths

Wave 0 may modify only PM-approved contract files under `app/domain/` plus focused contract tests and its task handoff. After that PR merges, contracts are frozen.

For Wave 1/2, Dev1 owns the retrieval/evidence implementation, expected under:

```text
app/rag/query_processing.py
app/rag/retrieval.py
app/rag/context.py
app/rag/citations.py
evaluation/datasets/
evaluation/reports/
tests/unit/rag/
tests/integration/rag/
docs/handoffs/P2-TASK-*.md
```

Exact filenames may be refined inside these areas. Do not edit API, generation, service wiring, dependencies, shared settings, phase docs, or coordinator state without approval.

## Functional Requirements

- Normalize without changing model codes, numbers, percentages, quotations, or negation.
- Invoke accepted Phase 1 embedding/vector-store boundaries for dense retrieval.
- Apply all explicit and mandatory system filters without leakage.
- Return ranked hits with complete provenance.
- Build deterministic, deduplicated, budget-bounded context with stable source IDs.
- Decide insufficient evidence before any LLM call.
- Reject unknown citations, unsupported quotes, and uncited factual claims.
- Produce a reproducible dense retrieval baseline without rewrite/rerank/hybrid.

## Technical Constraints

- One worktree/branch per stream; all PRs target `dev`.
- No FastAPI route, OpenAI SDK adapter, Agent framework, UI, or ingestion redesign.
- No public-contract change after Wave 0 without PM approval.
- Do not edit `AGENTS.md`, `feature_list.json`, `progress.md`, dependency files/lock, or Dev2-owned paths.
- Tests must not require network or a real LLM key.
- Qdrant tests must use isolated collections and must not delete unrelated data.

## Delivery Sequence

1. Submit `P2-TASK-01` on `feature/phase-02-contracts`; stop for review/merge.
2. Coordinator supplies the merged `dev` SHA.
3. Start `feature/phase-02-retrieval-evidence` from that SHA.
4. Implement P2-TASK-02, then P2-TASK-03, then P2-TASK-06 with focused commits.
5. Push and open a remote PR targeting `dev`; do not merge it.

## Acceptance and Quality Gates

Map evidence to AC-P2-01 through AC-P2-08, AC-P2-14 through AC-P2-17 as applicable. `./init.sh`, focused unit/integration tests, deterministic repeat checks, and the evaluation command must pass. The PR must include exact base/head SHAs and task handoff files.

## Forbidden Changes

- Query rewrite, reranking, sparse/hybrid retrieval, LLM-based filter inference.
- LLM generation/API code, Agent/LangGraph/Tool Calling, UI, CRM, OCR, or parser/chunker redesign.
- New service/dependency without PM decision.
- Direct push to `dev`/`main`, self-merge, skipped tests, or weaker ACs.

## Stop and Escalate

Stop with evidence if the accepted Phase 1 interfaces cannot support required search metadata/filters, the embedding/index identities disagree, a shared contract must break, or another owner’s file must change. Include affected Task/AC, options, trade-off, and recommendation.
