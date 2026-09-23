# Phase 01 Dev Evidence

## Handoff

- Phase: 01 — Document Ingestion + Vector DB
- Tasks: TASK-06, TASK-07, TASK-08; TASK-01–05 evidence retained in the existing baseline and benchmark records.
- Source branch: feature/phase-01-ingestion-qdrant
- Target branch: dev
- Status: PR #2 is open for QA; no remote status checks were reported at handoff.
- Commit / PR: 278c9f809430bbbf52d80277ae1491cc443857ac / https://github.com/BruceChun0820/pre-sales-knowledge-agent/pull/2

## Reproduction

1. Create the isolated environment using `docs/DEPENDENCY_BASELINE.md`.
2. Start Qdrant with `docker compose -f infra/docker-compose.yml up -d --wait`.
3. Configure the selected embedding model, immutable revision, dimension, and Qdrant URL in the environment.
4. Run `.venv/bin/python -m app.rag.ingestion.cli --data-root data/samples --metadata evaluation/configs/phase1_sample_metadata.json --manifest data/processed/phase1-sample-manifest.jsonl`.
5. Run `.venv/bin/ruff check .`, `.venv/bin/ruff format --check .`, and `.venv/bin/pytest -q`.

## Verification Evidence

- Qdrant: qdrant/qdrant:v1.19.1; Compose reports healthy; storage uses named volume qdrant_data; API port binds to 127.0.0.1 only.
- Automated quality: 52 tests passed; Ruff lint and formatter checks passed.
- Live Qdrant integration: 2 tests passed, including indexed-field filters, deterministic upsert, and Compose restart persistence.
- First sample CLI run: discovered=4, parsed=4, chunked=4, embedded=4, upserted=4, skipped=0, failed=0.
- Second unchanged CLI run: discovered=4, skipped=4, upserted=0, failed=0.
- Sample fixtures: synthetic PDF, DOCX, Markdown, and TXT; metadata is explicit in evaluation/configs/phase1_sample_metadata.json.
- Selected embedding: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 at e8f8c211226b894fcb81acc59f3b34ba3efd5f42; dimension 384.
- Candidate comparison and resource measurements: evaluation/reports/TASK-05-embedding-benchmark.md; selected rerun: evaluation/reports/TASK-05-selected-rerun.json.
- Persistence test restarts only the Compose Qdrant service and creates/deletes only a UUID-named test collection.
- Remote GitHub status-check list was empty at handoff; local quality gates are recorded above.

## Acceptance Criteria Mapping

| AC | Evidence |
|---|---|
| P1-01 | requirements-phase1.lock, requirements-embedding.lock, and Dependency Baseline clean-environment verification |
| P1-02–03 | parser golden tests; discovery path-escape tests; corrupt/unsupported per-document failures |
| P1-04–05 | deterministic chunking and text-preservation unit tests |
| P1-06–07 | ingestion pipeline tests for unchanged reruns, changed versions, and failed replacement |
| P1-08–09 | TASK-05 benchmark report and selected-model decision |
| P1-10–12 | Qdrant integration persistence/filter tests; typed model and dimension mismatch tests |
| P1-13 | first sample CLI summary reconciles four manifest records and four active Qdrant points |
| P1-14 | 52 passing tests; Ruff lint and format checks pass |
| P1-15 | no secrets, private customer data, model files, or Qdrant runtime storage intended for commit; tracked submission-path scan completed before push; no credential values or private/runtime data found |
| P1-16 | changes remain within Phase 1 scope; no LLM, API, Agent, OCR, hybrid search, or reranker |
| P1-17 | open PR https://github.com/BruceChun0820/pre-sales-knowledge-agent/pull/2 targets dev at tested head 278c9f809430bbbf52d80277ae1491cc443857ac; not merged |

## Known Limitations and QA Focus

- Scanned PDFs require OCR, which Phase 1 excludes.
- The index is local and single-tenant; only the configured demo tenant is supported.
- Retired document versions remain stored as inactive points to preserve rollback evidence.
- QA should focus on mandatory filter enforcement, collection model/dimension rejection, failed replacement safety, and persistence after restart.
- Embedding weights are downloaded from Hugging Face on first use and are not committed.
