# TASK-05 Embedding Benchmark Report

Status: `COMPLETED`

## Reproduction

```bash
.venv/bin/python scripts/benchmark_embeddings.py --config evaluation/configs/phase1_embedding_benchmark.json --output-json evaluation/reports/TASK-05-embedding-benchmark.json --output-markdown evaluation/reports/TASK-05-embedding-benchmark.md
```

The command exits non-zero when a candidate fails and still writes failure evidence.

## Dataset

- Dataset: `phase1-embedding-v1`
- Review status: `developer-reviewed`
- SHA-256: `3d09326857bceda531d2c93b31d3dc8c5b792547d0dae79bd643d189dd54515c`
- Shared corpus: 12 non-empty chunks
- Shared queries: 12 bilingual reviewed cases
- Provenance: Synthetic pre-sales product and solution statements created for Phase 1 evaluation.

## Candidate Results

| Candidate | Revision | Status | Hit Rate@5 | Recall@10 | Chunks/s | Query P50 ms | Query P95 ms | Peak RSS MiB | Dimension | Estimated index bytes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| multilingual-minilm | `e8f8c211226b894fcb81acc59f3b34ba3efd5f42` | succeeded | 1.0000 | 1.0000 | 107.3234 | 6.8370 | 9.9686 | 1385.7070 | 384 | 18432 |
| bge-m3-dense | `5617a9f61b028005a4858fdac845db406aefb181` | succeeded | 1.0000 | 1.0000 | 21.0255 | 32.7573 | 37.1974 | 2372.9141 | 1024 | 49152 |

## Decision Record

### Problem

Select one bilingual dense embedding model for Phase 1 using retrieval quality and CPU resource evidence.

### Options

1. Lightweight multilingual MiniLM (384 dimensions).
2. BGE-M3 dense mode (1024 dimensions).
3. Keep TASK-05 blocked until both candidates run on the same dataset.

### Decision

Selected `multilingual-minilm` for the Phase 1 baseline.

### Reason

Quality is within tolerance of the best candidate; selected the lower P95 latency, peak RSS, and index-size option for the CPU-only Phase 1 baseline.

### Trade-off

The smaller model may underperform BGE-M3 on a larger or harder corpus; repeat the benchmark when the reviewed evaluation set expands.

## Determinism

- Selection policy: Select candidates within metric tolerance of best Hit Rate@5 and Recall@10; then minimize query P95, peak RSS, and estimated float32 index size.
- Vector dimensions must match the pinned candidate configuration exactly.
- Retrieval metric tolerance across reruns is ±0.01.
- CPU device, normalized embeddings, corpus checksum, queries, and relevance labels are fixed.

## Selected Configuration Rerun

Evidence: `evaluation/reports/TASK-05-selected-rerun.json`.

```bash
.venv/bin/python scripts/verify_embedding_rerun.py --benchmark evaluation/reports/TASK-05-embedding-benchmark.json --rerun evaluation/reports/TASK-05-selected-rerun.json
```
