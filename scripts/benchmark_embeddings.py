from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.rag.benchmark import (
    EmbeddingBenchmarkConfig,
    EmbeddingCandidate,
    EvaluationDataset,
    evaluate_retrieval,
    load_config,
    load_dataset,
    percentile,
    select_candidate,
    write_json,
)
from app.rag.embeddings import SentenceTransformerEmbeddingProvider


def _current_rss_mb() -> float:
    status = Path("/proc/self/status")
    if not status.exists():
        return 0.0
    for line in status.read_text(encoding="utf-8").splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024
    return 0.0


class PeakRssSampler:
    def __init__(self) -> None:
        self.peak_mb = _current_rss_mb()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> float:
        self._stop.set()
        self._thread.join(timeout=1)
        self.peak_mb = max(self.peak_mb, _current_rss_mb())
        return self.peak_mb

    def _sample(self) -> None:
        while not self._stop.wait(0.01):
            self.peak_mb = max(self.peak_mb, _current_rss_mb())


def _run_candidate(
    config: EmbeddingBenchmarkConfig,
    candidate: EmbeddingCandidate,
    dataset: EvaluationDataset,
    dataset_checksum: str,
) -> tuple[dict[str, Any], bool]:
    sampler = PeakRssSampler()
    sampler.start()
    result: dict[str, Any] = {
        "candidate": candidate.model_dump(mode="json"),
        "dataset_id": dataset.dataset_id,
        "dataset_checksum": dataset_checksum,
        "chunk_count": len(dataset.chunks),
        "query_count": len(dataset.queries),
        "device": "cpu",
        "normalized": config.normalize_embeddings,
        "started_at": datetime.now(UTC).isoformat(),
    }
    succeeded = False
    try:
        load_started = time.perf_counter()
        provider = SentenceTransformerEmbeddingProvider(
            model_name=candidate.model_name,
            model_revision=candidate.model_revision,
            normalize_embeddings=config.normalize_embeddings,
            batch_size=config.batch_size,
        )
        result["model_load_seconds"] = time.perf_counter() - load_started
        if provider.dimension != candidate.expected_dimension:
            raise ValueError(
                f"dimension mismatch: expected {candidate.expected_dimension}, "
                f"got {provider.dimension}"
            )

        chunk_ids = tuple(chunk.chunk_id for chunk in dataset.chunks)
        chunk_texts = tuple(chunk.text for chunk in dataset.chunks)
        index_started = time.perf_counter()
        embeddings = provider.embed(chunk_texts, chunk_ids=chunk_ids)
        index_seconds = time.perf_counter() - index_started

        query_vectors: list[tuple[float, ...]] = []
        query_latencies_ms: list[float] = []
        for query in dataset.queries:
            query_started = time.perf_counter()
            query_vectors.append(provider.embed_queries((query.text,))[0])
            query_latencies_ms.append((time.perf_counter() - query_started) * 1000)

        metrics = evaluate_retrieval(
            chunk_ids=chunk_ids,
            document_vectors=embeddings.vectors,
            queries=dataset.queries,
            query_vectors=tuple(query_vectors),
        )
        result.update(
            {
                "status": "succeeded",
                "dimension": provider.dimension,
                "max_sequence_length": provider.max_sequence_length,
                "tokenizer_behavior": (
                    "Sentence-Transformers tokenizer; model truncation applies above "
                    "max_sequence_length; query/document encoders are used when available."
                ),
                "indexing_seconds": index_seconds,
                "indexing_throughput_chunks_per_second": len(dataset.chunks) / index_seconds,
                "query_latency_p50_ms": percentile(query_latencies_ms, 0.50),
                "query_latency_p95_ms": percentile(query_latencies_ms, 0.95),
                "estimated_index_size_bytes_float32": (
                    len(dataset.chunks) * provider.dimension * 4
                ),
                **metrics,
            }
        )
        succeeded = True
    except Exception as exc:
        result.update(
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
    finally:
        result["peak_rss_mb"] = sampler.stop()
        result["finished_at"] = datetime.now(UTC).isoformat()
    return result, succeeded


def _worker(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    candidate = next(item for item in config.candidates if item.key == args.candidate_key)
    dataset, checksum = load_dataset(config.dataset_path)
    result, succeeded = _run_candidate(config, candidate, dataset, checksum)
    write_json(args.worker_result, result)
    return 0 if succeeded else 1


def _candidate_failure(candidate: EmbeddingCandidate, message: str) -> dict[str, Any]:
    return {
        "candidate": candidate.model_dump(mode="json"),
        "status": "failed",
        "error_type": "BenchmarkProcessError",
        "error": message,
    }


def _run_all(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    dataset, dataset_checksum = load_dataset(config.dataset_path)
    results: list[dict[str, Any]] = []
    worker_environment = os.environ.copy()
    worker_environment.setdefault("HF_HUB_ETAG_TIMEOUT", "10")
    worker_environment.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "30")
    worker_environment.setdefault("HF_HUB_DISABLE_XET", "1")

    with tempfile.TemporaryDirectory(prefix="embedding-benchmark-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        for candidate in config.candidates:
            result_path = temporary_root / f"{candidate.key}.json"
            command = [
                sys.executable,
                str(Path(__file__).resolve()),
                "--config",
                str(args.config),
                "--candidate-key",
                candidate.key,
                "--worker-result",
                str(result_path),
            ]
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=config.candidate_timeout_seconds,
                    env=worker_environment,
                )
                if result_path.exists():
                    import json

                    result = json.loads(result_path.read_text(encoding="utf-8"))
                    result["reproduction_command"] = (
                        f"{sys.executable} scripts/benchmark_embeddings.py --config {args.config}"
                    )
                    results.append(result)
                else:
                    message = completed.stderr.strip() or completed.stdout.strip()
                    results.append(
                        _candidate_failure(candidate, message or "worker wrote no result")
                    )
            except subprocess.TimeoutExpired:
                results.append(
                    _candidate_failure(
                        candidate,
                        f"candidate exceeded {config.candidate_timeout_seconds}-second timeout",
                    )
                )

    failures = [result for result in results if result["status"] != "succeeded"]
    decision = select_candidate(results, config.deterministic_metric_tolerance)
    payload = {
        "benchmark_id": config.benchmark_id,
        "status": "blocked" if failures else "completed",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": {
            "dataset_id": dataset.dataset_id,
            "review_status": dataset.review_status,
            "provenance": dataset.provenance,
            "checksum": dataset_checksum,
            "chunk_count": len(dataset.chunks),
            "query_count": len(dataset.queries),
        },
        "configuration": config.model_dump(mode="json"),
        "runtime": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "results": results,
        "decision": decision,
    }
    write_json(args.output_json, payload)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.write_text(_render_markdown(payload), encoding="utf-8")
    return 1 if failures else 0


def _format_metric(result: dict[str, Any], key: str) -> str:
    value = result.get(key)
    return f"{value:.4f}" if isinstance(value, float) else "N/A"


def _render_markdown(payload: dict[str, Any]) -> str:
    dataset = payload["dataset"]
    tolerance = payload["configuration"]["deterministic_metric_tolerance"]
    reproduce = (
        ".venv/bin/python scripts/benchmark_embeddings.py "
        "--config evaluation/configs/phase1_embedding_benchmark.json "
        "--output-json evaluation/reports/TASK-05-embedding-benchmark.json "
        "--output-markdown evaluation/reports/TASK-05-embedding-benchmark.md"
    )
    lines = [
        "# TASK-05 Embedding Benchmark Report",
        "",
        f"Status: `{str(payload['status']).upper()}`",
        "",
        "## Reproduction",
        "",
        "```bash",
        reproduce,
        "```",
        "",
        "The command exits non-zero when a candidate fails and still writes failure evidence.",
        "",
        "## Dataset",
        "",
        f"- Dataset: `{dataset['dataset_id']}`",
        f"- Review status: `{dataset['review_status']}`",
        f"- SHA-256: `{dataset['checksum']}`",
        f"- Shared corpus: {dataset['chunk_count']} non-empty chunks",
        f"- Shared queries: {dataset['query_count']} bilingual reviewed cases",
        f"- Provenance: {dataset['provenance']}",
        "",
        "## Candidate Results",
        "",
        (
            "| Candidate | Revision | Status | Hit Rate@5 | Recall@10 | Chunks/s | "
            "Query P50 ms | Query P95 ms | Peak RSS MiB | Dimension | Estimated index bytes |"
        ),
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in payload["results"]:
        candidate = result["candidate"]
        lines.append(
            "| {key} | `{revision}` | {status} | {hit} | {recall} | {throughput} | "
            "{p50} | {p95} | {rss} | {dimension} | {size} |".format(
                key=candidate["key"],
                revision=candidate["model_revision"],
                status=result["status"],
                hit=_format_metric(result, "hit_rate_at_5"),
                recall=_format_metric(result, "recall_at_10"),
                throughput=_format_metric(result, "indexing_throughput_chunks_per_second"),
                p50=_format_metric(result, "query_latency_p50_ms"),
                p95=_format_metric(result, "query_latency_p95_ms"),
                rss=_format_metric(result, "peak_rss_mb"),
                dimension=result.get("dimension", "N/A"),
                size=result.get("estimated_index_size_bytes_float32", "N/A"),
            )
        )
    lines.append("")

    failures = [result for result in payload["results"] if result["status"] != "succeeded"]
    if failures:
        lines.extend(["", "## Reproducible Failures", ""])
        for result in failures:
            candidate = result["candidate"]
            lines.extend(
                [
                    f"### {candidate['key']}",
                    "",
                    f"- Model: `{candidate['model_name']}`",
                    f"- Revision: `{candidate['model_revision']}`",
                    f"- Error type: `{result.get('error_type', 'unknown')}`",
                    f"- Error: {result.get('error', 'unknown')}",
                    "",
                ]
            )

    lines.extend(
        [
            "## Decision Record",
            "",
            "### Problem",
            "",
            (
                "Select one bilingual dense embedding model for Phase 1 using retrieval "
                "quality and CPU resource evidence."
            ),
            "",
            "### Options",
            "",
            "1. Lightweight multilingual MiniLM (384 dimensions).",
            "2. BGE-M3 dense mode (1024 dimensions).",
            "3. Keep TASK-05 blocked until both candidates run on the same dataset.",
            "",
            "### Decision",
            "",
        ]
    )
    decision = payload["decision"]
    if decision["status"] == "selected":
        lines.append(f"Selected `{decision['selected_candidate']}` for the Phase 1 baseline.")
    else:
        lines.append("`BLOCKED`: no embedding model is selected.")
    lines.extend(
        [
            "",
            "### Reason",
            "",
            str(decision["reason"]),
            "",
            "### Trade-off",
            "",
            str(decision.get("trade_off", "Selection remains blocked until all candidates run.")),
            "",
            "## Determinism",
            "",
            f"- Selection policy: {payload['configuration']['selection_policy']}",
            "- Vector dimensions must match the pinned candidate configuration exactly.",
            f"- Retrieval metric tolerance across reruns is ±{tolerance:.2f}.",
            (
                "- CPU device, normalized embeddings, corpus checksum, queries, and "
                "relevance labels are fixed."
            ),
            "",
            "## Selected Configuration Rerun",
            "",
            "Evidence: `evaluation/reports/TASK-05-selected-rerun.json`.",
            "",
            "```bash",
            (
                ".venv/bin/python scripts/verify_embedding_rerun.py "
                "--benchmark evaluation/reports/TASK-05-embedding-benchmark.json "
                "--rerun evaluation/reports/TASK-05-selected-rerun.json"
            ),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark pinned CPU embedding candidates")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-markdown", type=Path)
    parser.add_argument("--candidate-key")
    parser.add_argument("--worker-result", type=Path)
    args = parser.parse_args()
    worker_mode = bool(args.candidate_key or args.worker_result)
    if worker_mode and not (args.candidate_key and args.worker_result):
        parser.error("worker mode requires --candidate-key and --worker-result")
    if not worker_mode and not (args.output_json and args.output_markdown):
        parser.error("benchmark mode requires --output-json and --output-markdown")
    return args


def main() -> int:
    args = _parse_args()
    if args.candidate_key:
        return _worker(args)
    return _run_all(args)


if __name__ == "__main__":
    raise SystemExit(main())
