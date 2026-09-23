from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path
from typing import Any

from app.core.settings import Settings
from app.domain.contracts import SearchRequest, SearchStatus
from app.domain.models import Chunk
from app.rag.embeddings import SentenceTransformerEmbeddingProvider
from app.rag.retrieval import DenseRetriever
from app.rag.vector_store import QdrantVectorStore

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation/datasets/phase2_retrieval_v1.json"
DEFAULT_OUTPUT = ROOT / "evaluation/reports/phase2_retrieval_baseline_v1.json"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_chunks(client: Any, collection_name: str) -> tuple[Chunk, ...]:
    chunks: list[Chunk] = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection_name,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            chunks.append(
                Chunk.model_validate(
                    {key: value for key, value in payload.items() if key in Chunk.model_fields}
                )
            )
        if offset is None:
            break
    return tuple(sorted(chunks, key=lambda chunk: chunk.chunk_id))


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 4)


def _hit_details(response: Any) -> list[dict[str, Any]]:
    return [
        {
            "rank": hit.rank,
            "score": hit.score,
            "chunk_id": hit.chunk_id,
            "document_id": hit.document_id,
            "document_version": hit.document_version,
            "source_uri": hit.source_uri,
            "source_location": hit.source_location.model_dump(mode="json"),
        }
        for hit in response.hits
    ]


def _run_case(retriever: DenseRetriever, case: dict[str, Any], config: dict[str, Any]):
    request = SearchRequest(
        query=case["query"],
        top_k=config["candidate_k"],
        filters=config["filters"],
    )
    request_id = "eval-" + case["case_id"]
    first = retriever.search(request, request_id=request_id)
    repeated = retriever.search(request, request_id=request_id)

    first_ids = [hit.chunk_id for hit in first.hits]
    repeated_ids = [hit.chunk_id for hit in repeated.hits]
    score_diffs = []
    if first_ids == repeated_ids:
        score_diffs = [
            abs(left.score - right.score)
            for left, right in zip(first.hits, repeated.hits, strict=True)
        ]
    repeat_ok = (
        first.status == repeated.status
        and first_ids == repeated_ids
        and all(value <= config["score_tolerance"] for value in score_diffs)
    )

    expected = set(case["expected_chunk_ids"])
    relevant_at_5 = expected.intersection(first_ids[:5])
    relevant_at_10 = expected.intersection(first_ids[:10])
    if case["unanswerable"]:
        hit_at_5 = None
        recall_at_10 = None
        reciprocal_rank = None
    else:
        hit_at_5 = bool(relevant_at_5)
        recall_at_10 = len(relevant_at_10) / len(expected) if expected else 0.0
        relevant_ranks = [
            index + 1 for index, chunk_id in enumerate(first_ids) if chunk_id in expected
        ]
        reciprocal_rank = 1 / min(relevant_ranks) if relevant_ranks else 0.0

    failure = None
    issues = []
    if first.status == SearchStatus.FAILED:
        failure = {
            "code": first.failure.code.value if first.failure else "unknown",
            "stage": first.failure.details.get("stage") if first.failure else None,
        }
        issues.append({"code": "retrieval_failed", "failure": failure})
    elif case["unanswerable"] and first.hits:
        issues.append(
            {
                "code": "unanswerable_candidates_returned",
                "candidate_count": len(first.hits),
            }
        )
    elif expected.difference(first_ids):
        issues.append(
            {
                "code": "expected_chunks_not_retrieved",
                "missing_chunk_ids": sorted(expected.difference(first_ids)),
            }
        )
    return {
        "case_id": case["case_id"],
        "slices": case["slices"],
        "unanswerable": case["unanswerable"],
        "expected_chunk_ids": sorted(expected),
        "retrieved_expected_chunk_ids": sorted(expected.intersection(first_ids)),
        "missing_expected_chunk_ids": sorted(expected.difference(first_ids)),
        "status": first.status.value,
        "retrieved": _hit_details(first),
        "best_score": first.hits[0].score if first.hits else None,
        "hit_rate_at_5": hit_at_5,
        "recall_at_10": recall_at_10,
        "reciprocal_rank": reciprocal_rank,
        "unanswerable_returned_candidates": len(first.hits) if case["unanswerable"] else None,
        "latency_ms": first.trace.latency_ms if first.trace else None,
        "failure": failure,
        "issues": issues,
        "repeat_check": {
            "passed": repeat_ok,
            "ordered_chunk_ids_match": first_ids == repeated_ids,
            "max_score_delta": max(score_diffs, default=0.0),
        },
    }


def _aggregate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [case for case in cases if not case["unanswerable"]]
    recalls = [case["recall_at_10"] for case in answerable]
    mrr_values = [case["reciprocal_rank"] for case in answerable]
    latencies = [case["latency_ms"] for case in cases if case["latency_ms"] is not None]
    answerable_best = [
        case.get("best_score") for case in answerable if case.get("best_score") is not None
    ]
    unanswerable = [case for case in cases if case["unanswerable"]]
    unanswerable_best = [
        case.get("best_score") for case in unanswerable if case.get("best_score") is not None
    ]
    all_slices = sorted({tag for case in cases for tag in case["slices"]})
    slices = {}
    for tag in all_slices:
        selected = [case for case in cases if tag in case["slices"]]
        eligible = [case for case in selected if not case["unanswerable"]]
        slices[tag] = {
            "case_count": len(selected),
            "answerable_count": len(eligible),
            "hit_rate_at_5": (
                sum(case["hit_rate_at_5"] for case in eligible) / len(eligible)
                if eligible
                else None
            ),
            "recall_at_10": (
                sum(case["recall_at_10"] for case in eligible) / len(eligible) if eligible else None
            ),
            "unanswerable_candidate_cases": sum(
                case["unanswerable"] and case["unanswerable_returned_candidates"] > 0
                for case in selected
            ),
            "failures": sum(case["status"] == SearchStatus.FAILED.value for case in selected),
        }
    return {
        "answerable_case_count": len(answerable),
        "unanswerable_case_count": len(cases) - len(answerable),
        "hit_rate_at_5": (
            sum(case["hit_rate_at_5"] for case in answerable) / len(answerable)
            if answerable
            else None
        ),
        "recall_at_10": sum(recalls) / len(recalls) if recalls else None,
        "eligible_mrr": sum(mrr_values) / len(mrr_values) if mrr_values else None,
        "score_calibration": {
            "minimum_answerable_best_score": min(answerable_best) if answerable_best else None,
            "maximum_unanswerable_best_score": max(unanswerable_best)
            if unanswerable_best
            else None,
            "score_separation_observed": (
                min(answerable_best) > max(unanswerable_best)
                if answerable_best and unanswerable_best
                else None
            ),
            "interpretation": (
                "diagnostic only; this small synthetic sample does not set a production "
                "evidence threshold"
            ),
        },
        "unanswerable_returned_candidates": sum(
            case["unanswerable_returned_candidates"] > 0 for case in cases if case["unanswerable"]
        ),
        "latency_ms": {
            "count": len(latencies),
            "min": round(min(latencies), 4) if latencies else None,
            "p50": _percentile(latencies, 0.50),
            "p95": _percentile(latencies, 0.95),
            "max": round(max(latencies), 4) if latencies else None,
        },
        "failure_count": sum(case["status"] == SearchStatus.FAILED.value for case in cases),
        "missed_expected_chunk_count": sum(
            len(case["missing_expected_chunk_ids"]) for case in answerable
        ),
        "cases_with_missed_expected_chunks": sum(
            bool(case["missing_expected_chunk_ids"]) for case in answerable
        ),
        "slices": slices,
    }


def _repository_revision() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run(dataset_path: Path, output_path: Path) -> dict[str, Any]:
    dataset_bytes = dataset_path.read_bytes()
    dataset = json.loads(dataset_bytes)
    if dataset.get("schema_version") != 1:
        raise ValueError("unsupported evaluation dataset schema version")
    corpus = dataset["corpus"]
    config = dataset["retrieval_config"]
    cases = dataset["cases"]
    if (
        not cases
        or len({case.get("case_id") for case in cases}) != len(cases)
        or any(
            ("unanswerable" not in case)
            or (case["unanswerable"] and case["expected_chunk_ids"])
            or (not case["unanswerable"] and not case["expected_chunk_ids"])
            for case in cases
        )
    ):
        raise ValueError("evaluation cases require relevant IDs or an explicit unanswerable label")

    settings = Settings()
    from qdrant_client import QdrantClient

    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None,
        timeout=10,
    )
    try:
        collection_info = client.get_collection(corpus["qdrant_collection"])
        metadata = collection_info.config.metadata or {}
        expected_metadata = {
            "embedding_model": corpus["embedding_model"],
            "embedding_model_revision": corpus["embedding_revision"],
            "embedding_dimension": corpus["embedding_dimension"],
        }
        if metadata != expected_metadata:
            raise ValueError("active collection embedding identity differs from the frozen dataset")
        chunks = _load_chunks(client, corpus["qdrant_collection"])
        active_chunks = tuple(chunk for chunk in chunks if chunk.active)
        if len(active_chunks) != corpus["expected_active_points"]:
            raise ValueError("active collection point count differs from the frozen dataset")
        active_ids = {chunk.chunk_id for chunk in active_chunks}
        expected_ids = {chunk_id for case in cases for chunk_id in case["expected_chunk_ids"]}
        if not expected_ids.issubset(active_ids):
            raise ValueError("evaluation dataset references chunks absent from the active index")

        provider = SentenceTransformerEmbeddingProvider(
            model_name=corpus["embedding_model"],
            model_revision=corpus["embedding_revision"],
            normalize_embeddings=True,
            local_files_only=True,
        )
        if provider.dimension != corpus["embedding_dimension"]:
            raise ValueError("loaded embedding model dimension differs from the frozen dataset")
        store = QdrantVectorStore(
            client,
            collection_name=corpus["qdrant_collection"],
            model_name=corpus["embedding_model"],
            model_revision=corpus["embedding_revision"],
            dimension=corpus["embedding_dimension"],
        )
        retriever = DenseRetriever(provider, store)
        per_case = [_run_case(retriever, case, config) for case in cases]

        identity = [
            {
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "document_version": chunk.document_version,
                "content_checksum": chunk.content_checksum,
                "text_checksum": chunk.text_checksum,
                "source_uri": chunk.source_uri,
                "parser_version": chunk.parser_version,
                "cleaner_version": chunk.cleaner_version,
                "chunker_version": chunk.chunker_version,
                "active": chunk.active,
            }
            for chunk in active_chunks
        ]
        corpus_fingerprint = _sha256_bytes(_canonical_json(identity).encode())
        chunk_versions = {
            key: sorted({getattr(chunk, key) for chunk in active_chunks})
            for key in ("parser_version", "cleaner_version", "chunker_version")
        }
        repeat_passed = all(case["repeat_check"]["passed"] for case in per_case)
        report = {
            "report_id": "phase2-retrieval-baseline-v1",
            "dataset": {
                "schema_version": dataset["schema_version"],
                "dataset_id": dataset["dataset_id"],
                "review_status": dataset["review_status"],
                "sha256": _sha256_bytes(dataset_bytes),
                "case_count": len(cases),
                "provenance": dataset["provenance"],
            },
            "corpus": {
                "qdrant_url": settings.qdrant_url,
                "collection": corpus["qdrant_collection"],
                "active_point_count": len(active_chunks),
                "active_payload_fingerprint_sha256": corpus_fingerprint,
                "chunk_versions": chunk_versions,
                "chunk_config": {
                    "runtime_settings": {
                        "target_tokens": settings.chunk_target_tokens,
                        "max_tokens": settings.chunk_max_tokens,
                        "overlap_tokens": settings.chunk_overlap_tokens,
                    },
                    "ingestion_time_config_persisted": False,
                    "note": (
                        "Runtime values are current Settings; Phase 1 payloads retain only chunker "
                        "version, not numeric ingestion settings."
                    ),
                },
            },
            "embedding": {
                "model": provider.model_name,
                "revision": provider.model_revision,
                "dimension": provider.dimension,
                "device": "cpu",
                "normalized": provider.normalized,
                "torch_version": __import__("torch").__version__,
                "cuda_available": __import__("torch").cuda.is_available(),
            },
            "configuration": {
                "query_normalization": "NFKC + trim; no rewrite",
                "retrieval": "dense only; Qdrant order preserved; no reranker or hybrid search",
                "candidate_k": config["candidate_k"],
                "filters": config["filters"],
                "score_metric": "cosine",
                "aggregation": "macro average over answerable cases",
                "score_method": (
                    "Re-embed returned candidates using the exact indexed model revision to "
                    "populate score metadata; preserve Qdrant's dense result order."
                ),
                "score_repeat_tolerance": config["score_tolerance"],
                "deterministic_tolerance": (
                    "ordered chunk IDs exact; score delta <= score_repeat_tolerance; "
                    "latency is informational and is not compared."
                ),
            },
            "code_revision": _repository_revision(),
            "metrics": _aggregate(per_case),
            "repeat_check": {
                "passed": repeat_passed,
                "all_case_order_and_score_checks_passed": repeat_passed,
            },
            "cases": per_case,
            "case_issues": [
                {"case_id": case["case_id"], "issues": case["issues"]}
                for case in per_case
                if case["issues"]
            ],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return report
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the frozen dense retrieval baseline.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = run(args.dataset, args.output)
    print(
        json.dumps(
            {
                "report": str(args.output),
                "code_revision": report["code_revision"],
                "hit_rate_at_5": report["metrics"]["hit_rate_at_5"],
                "recall_at_10": report["metrics"]["recall_at_10"],
                "eligible_mrr": report["metrics"]["eligible_mrr"],
                "repeat_check": report["repeat_check"]["passed"],
                "failure_count": report["metrics"]["failure_count"],
            },
            sort_keys=True,
        )
    )
    return 0 if report["repeat_check"]["passed"] and report["metrics"]["failure_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
