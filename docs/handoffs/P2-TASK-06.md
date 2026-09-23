# P2-TASK-06 Handoff - Retrieval Baseline and Regression Evidence

## Delivery

- Status: implementation complete; submitted for QA/PM review.
- Branch: `feature/phase-02-dev1-retrieval-evidence`
- Accepted base: `268c6674771984d2b844195f291263ae265b342d`
- Commit: `2fb53342fb9b8fef48f8c1bafebee9524099534e`
- Dataset: `evaluation/datasets/phase2_retrieval_v1.json`
- Runner: `evaluation/run_phase2_retrieval.py`
- Report: `evaluation/reports/phase2_retrieval_baseline_v1.json`
- PR: pending final submission.

## Reproduction and results

Run from the repository root with the documented CPU embedding environment and local Phase 1 Qdrant fixture:

```sh
.venv/bin/python evaluation/run_phase2_retrieval.py --output evaluation/reports/phase2_retrieval_baseline_v1.json
```

Dataset contains five developer-reviewed cases over four synthetic Phase 1 chunks. It records explicit answerable/unanswerable labels, expected chunk IDs, slices, filters, K, and score repeat tolerance.

- Hit Rate@5: 1.0 (4 answerable cases)
- Recall@10: 1.0
- Eligible MRR: 1.0
- Backend failures: 0; expected chunks missed: 0
- Repeated ordered IDs exact and score delta 0.0 (tolerance 1e-5)
- Latency is reported per case and as min/p50/p95/max; it is informational.
- Dataset SHA, corpus fingerprint, active count, embedding model/revision/dimension, chunk/parser/cleaner versions, runtime chunk settings, filters, K, and code revision are recorded.
- Post-commit repeat matched dataset/corpus/model/config, retrieval metrics, score diagnostics, repeat checks, and ordered IDs. Latency naturally varied.

## Limitations and QA notes

One explicit unanswerable encryption question returned four dense candidates. This is recorded as `unanswerable_candidates_returned`; the best-score separation is diagnostic only. The sample is too small and synthetic to establish a production evidence threshold. Do not tune a holdout or promote a threshold from these results.

Phase 1 payloads persist chunker version but not numeric ingestion-time chunk settings; the report explicitly labels current Settings values as runtime values. The runner does not mutate or delete Qdrant points; constructing the existing adapter may idempotently ensure payload indexes. Local-Qdrant integration tests emit the expected no-op payload-index warning.

`./init.sh`: 93 passed; Ruff lint, format, whitespace/conflict checks passed. No generation/API/dependency/shared tracker changes.
