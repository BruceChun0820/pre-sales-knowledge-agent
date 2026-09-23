# P2-TASK-01 Handoff — Contract Gate

## Delivery

- Task: `P2-TASK-01` — Freeze Domain/API Contracts and Test Doubles
- Branch: `feature/phase-02-contracts`
- Base branch: `main`
- Base/start commit: `6a5da8782701bdd59a0b2ae07dede273b416a488` (Phase 2 activation commit; parent `cb31243f410b4eab0f8c240b21622e9324d622b3`)
- Implementation commit and initial submitted PR head: `1ee187c2553d0993d24fbb5be164c2de77cd047e`.
- Pull request: [#9](https://github.com/BruceChun0820/pre-sales-knowledge-agent/pull/9), open and targeting `main`.
- Final review head after this handoff update is recorded in the PR description and GitHub PR metadata.
- Worktree: `/home/bruce/Dev/pre-sales-knowledge-agent-phase2-contracts`

## Scope Delivered

Added framework-neutral contracts for typed search requests, explicit filters, ranked search hits and results, evidence sources/context, answer/claim/citation responses, trace/usage metrics, typed failures, generation requests/results, and search/query/provider protocols. Added deterministic search and provider test doubles. No endpoint, retrieval algorithm, real provider call, or dependency was added.

## Acceptance Evidence

| P2-TASK-01 criterion | Evidence |
|---|---|
| Empty query, invalid top-k, unknown enum, and malformed/unauthorized filters fail with typed validation errors | `tests/unit/test_phase2_contracts.py::test_search_request_rejects_invalid_query_k_enum_and_filters` covers blank query, K values 0/101, invalid document type, malformed labels, and forbidden tenant/active/unknown fields; Pydantic `ValidationError`. |
| Search hits serialize rank, score, chunk/document/version identity, and source location | `test_search_hit_serializes_rank_score_identity_and_source_location`; `SearchHit.from_chunk` adapts the accepted Phase 1 `Chunk` boundary without changing it. |
| Query responses serialize all terminal statuses, claims, citations, warnings, metrics, and request ID | `test_query_response_serializes_each_terminal_status`; invalid status/data combinations and inconsistent usage are covered separately. |
| Contracts import without FastAPI, Qdrant, or OpenAI SDK | `test_contract_import_succeeds_when_infrastructure_and_provider_sdks_are_blocked` installs an import blocker for FastAPI, Qdrant, OpenAI, LangChain, and LangGraph before importing contracts/fakes. |
| Deterministic fakes cover retrieval success/empty/failure and LLM success/malformed/failure | `test_fake_search_supports_success_empty_and_failure_deterministically` and parameterized `test_fake_llm_supports_all_provider_paths`; repeated search outputs compare byte-for-byte JSON serialization. |

## Files Changed

- `app/domain/contracts.py` — Phase 2 public domain contracts and protocols.
- `app/domain/fakes.py` — deterministic test doubles only.
- `tests/unit/test_phase2_contracts.py` — validation, serialization, SDK isolation, and fake-path tests.
- `docs/handoffs/P2-TASK-01.md` — this evidence record.

No shared tracker, Phase plan, dependency/lock file, retrieval implementation, generation adapter, API route, or Phase 1 model/interface was changed.

## Commands and Results

- Initial `./init.sh`: stopped with exit 2 because the new remote worktree had no complete `.venv`.
- Followed `docs/DEPENDENCY_BASELINE.md`: created isolated `.venv` and installed existing `requirements-phase1.lock`; no dependency files were changed.
- `.venv/bin/python -m pytest tests/unit/test_phase2_contracts.py -q`: **19 passed**.
- `./init.sh`: **PASS** — 73 tests passed; Ruff lint passed; 72 files already formatted; whitespace/conflict check passed. One pre-existing in-memory Qdrant payload-index warning was emitted by the Phase 1 ingestion integration test.
- GitHub CLI was not present on Ubuntu; PR submission uses the connected GitHub integration.

## Limitations and Reproduction

The fakes are contract test doubles, not retrieval or generation implementations. Search filter translation, retrieval ranking, evidence sufficiency, provider SDK integration, endpoints, and orchestration remain owned by later tasks. The malformed-provider fake preserves only JSON-shaped raw values.

Reproduce from the remote worktree with:

```bash
.venv/bin/python -m pytest tests/unit/test_phase2_contracts.py -q
./init.sh
```

The initial submitted PR head was `1ee187c2553d0993d24fbb5be164c2de77cd047e`; the PR head after this handoff update is stated in the PR description and GitHub metadata. QA should check out that exact remote head and rerun `./init.sh`. No merge was performed. Dev2 remains read-only until PM/QA approve and merge the contract PR; after merge, wait for PM's exact resulting `main` SHA before retrieval work.
