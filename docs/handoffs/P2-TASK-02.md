# P2-TASK-02 Handoff - Query Processing and Dense Retrieval

## Delivery

- Status: implementation complete; submitted for QA/PM review.
- Branch: `feature/phase-02-dev1-retrieval-evidence`
- Accepted base: `268c6674771984d2b844195f291263ae265b342d`
- Commits: `bb20851095fe8a449a3d10cad9f062ca10ed8b75` (retrieval); `422fc12` (preserve Qdrant ordering follow-up)
- PR: pending final submission.

## Acceptance evidence

- AC-P2-02: NFKC plus trim normalization preserves punctuation, identifiers, numbers and negation. Unit coverage in `tests/unit/rag/test_query_processing.py`.
- AC-P2-03: dense Qdrant search returns typed ranked hits with chunk/document/version/source location; system tenant/document/version scope is injected and conflicts fail closed. Unit and in-memory Qdrant tests cover active/positive/negative filters, scope and typed errors.
- AC-P2-04: query normalization and Qdrant order are deterministic for unchanged input/index. Repeat baseline confirms exact ordered IDs and score tolerance.
- AC-P2-14: baseline records model/index/config/code identity; see `evaluation/reports/phase2_retrieval_baseline_v1.json`.
- AC-P2-16: dense retrieval only; no rewrite, reranker, sparse/hybrid search, generation or API wiring.

## Validation

- Focused retrieval unit/integration tests passed.
- `./init.sh`: 93 passed; Ruff lint, format, whitespace/conflict checks passed.
- One expected local-Qdrant warning: payload indexes are no-ops in local in-memory Qdrant.

## Implementation note and limitation

The accepted `VectorStore.search()` returns chunks without scores, and the Qdrant adapter discards Qdrant scores. To populate frozen `SearchHit.score` without changing shared contracts or the adapter, the retriever re-embeds only bounded returned candidate texts with the exact indexed model revision and computes cosine score metadata. It preserves the vector store ranking. This adds bounded embedding cost; score values are metadata and are not used to rerank.

## QA notes

No generation is triggered by retrieval. No shared contract, API, dependency, service, tracker, or other-owner file was changed.
