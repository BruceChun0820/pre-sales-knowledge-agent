from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BenchmarkModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvaluationChunk(BenchmarkModel):
    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


class EvaluationQuery(BenchmarkModel):
    query_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    relevant_chunk_ids: tuple[str, ...] = Field(min_length=1)


class EvaluationDataset(BenchmarkModel):
    dataset_id: str = Field(min_length=1)
    review_status: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    chunks: tuple[EvaluationChunk, ...] = Field(min_length=1)
    queries: tuple[EvaluationQuery, ...] = Field(min_length=10)

    @model_validator(mode="after")
    def validate_identity_and_relevance(self) -> EvaluationDataset:
        chunk_ids = [chunk.chunk_id for chunk in self.chunks]
        query_ids = [query.query_id for query in self.queries]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("chunk IDs must be unique")
        if len(query_ids) != len(set(query_ids)):
            raise ValueError("query IDs must be unique")
        unknown = {
            relevant_id
            for query in self.queries
            for relevant_id in query.relevant_chunk_ids
            if relevant_id not in set(chunk_ids)
        }
        if unknown:
            raise ValueError(f"queries reference unknown chunks: {sorted(unknown)}")
        return self


class EmbeddingCandidate(BenchmarkModel):
    key: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    model_revision: str = Field(min_length=7)
    expected_dimension: int = Field(ge=1)


class EmbeddingBenchmarkConfig(BenchmarkModel):
    benchmark_id: str = Field(min_length=1)
    dataset_path: Path
    device: str
    batch_size: int = Field(ge=1)
    normalize_embeddings: bool
    candidate_timeout_seconds: int = Field(ge=1)
    deterministic_metric_tolerance: float = Field(ge=0, le=1)
    selection_policy: str = Field(min_length=1)
    candidates: tuple[EmbeddingCandidate, ...] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_cpu_and_candidates(self) -> EmbeddingBenchmarkConfig:
        if self.device != "cpu":
            raise ValueError("Phase 1 embedding benchmark must use CPU")
        keys = [candidate.key for candidate in self.candidates]
        if len(keys) != len(set(keys)):
            raise ValueError("candidate keys must be unique")
        return self


def load_dataset(path: Path) -> tuple[EvaluationDataset, str]:
    raw = path.read_bytes()
    dataset = EvaluationDataset.model_validate_json(raw)
    return dataset, hashlib.sha256(raw).hexdigest()


def load_config(path: Path) -> EmbeddingBenchmarkConfig:
    return EmbeddingBenchmarkConfig.model_validate_json(path.read_text(encoding="utf-8"))


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have equal dimensions")
    dot_product = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def evaluate_retrieval(
    *,
    chunk_ids: tuple[str, ...],
    document_vectors: tuple[tuple[float, ...], ...],
    queries: tuple[EvaluationQuery, ...],
    query_vectors: tuple[tuple[float, ...], ...],
) -> dict[str, object]:
    if len(chunk_ids) != len(document_vectors):
        raise ValueError("chunk IDs and document vectors must have equal lengths")
    if len(queries) != len(query_vectors):
        raise ValueError("queries and query vectors must have equal lengths")

    hit_values: list[float] = []
    recall_values: list[float] = []
    per_query: list[dict[str, object]] = []
    for query, query_vector in zip(queries, query_vectors, strict=True):
        ranked = sorted(
            (
                (chunk_id, cosine_similarity(query_vector, document_vector))
                for chunk_id, document_vector in zip(
                    chunk_ids,
                    document_vectors,
                    strict=True,
                )
            ),
            key=lambda item: (-item[1], item[0]),
        )
        top_five = {chunk_id for chunk_id, _ in ranked[:5]}
        top_ten = {chunk_id for chunk_id, _ in ranked[:10]}
        relevant = set(query.relevant_chunk_ids)
        hit = float(bool(top_five & relevant))
        recall = len(top_ten & relevant) / len(relevant)
        hit_values.append(hit)
        recall_values.append(recall)
        per_query.append(
            {
                "query_id": query.query_id,
                "hit_at_5": bool(hit),
                "recall_at_10": recall,
                "top_chunk_ids": [chunk_id for chunk_id, _ in ranked[:10]],
            }
        )

    return {
        "hit_rate_at_5": sum(hit_values) / len(hit_values),
        "recall_at_10": sum(recall_values) / len(recall_values),
        "per_query": per_query,
    }


def percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between zero and one")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def select_candidate(results: list[dict[str, object]], tolerance: float) -> dict[str, object]:
    """Select the lowest-cost candidate whose quality is within deterministic tolerance."""

    if not results or any(result.get("status") != "succeeded" for result in results):
        return {
            "status": "blocked",
            "selected_candidate": None,
            "reason": "Every pinned candidate must succeed before model selection.",
        }
    best_hit = max(float(result["hit_rate_at_5"]) for result in results)
    best_recall = max(float(result["recall_at_10"]) for result in results)
    eligible = [
        result
        for result in results
        if best_hit - float(result["hit_rate_at_5"]) <= tolerance
        and best_recall - float(result["recall_at_10"]) <= tolerance
    ]
    selected = min(
        eligible,
        key=lambda result: (
            float(result["query_latency_p95_ms"]),
            float(result["peak_rss_mb"]),
            int(result["estimated_index_size_bytes_float32"]),
        ),
    )
    candidate = selected["candidate"]
    if not isinstance(candidate, dict):
        raise ValueError("candidate result metadata must be a mapping")
    return {
        "status": "selected",
        "selected_candidate": candidate["key"],
        "reason": (
            "Quality is within tolerance of the best candidate; selected the lower P95 "
            "latency, peak RSS, and index-size option for the CPU-only Phase 1 baseline."
        ),
        "trade_off": (
            "The smaller model may underperform BGE-M3 on a larger or harder corpus; "
            "repeat the benchmark when the reviewed evaluation set expands."
        ),
    }


def verify_selected_rerun(
    benchmark: dict[str, object],
    rerun: dict[str, object],
) -> dict[str, object]:
    """Verify selected-model dimensions and retrieval metrics across an independent rerun."""

    decision = benchmark.get("decision")
    configuration = benchmark.get("configuration")
    results = benchmark.get("results")
    if not isinstance(decision, dict) or decision.get("status") != "selected":
        raise ValueError("benchmark does not contain a selected candidate")
    if not isinstance(configuration, dict) or not isinstance(results, list):
        raise ValueError("benchmark result has invalid configuration or results")
    selected_key = decision.get("selected_candidate")
    baseline = next(
        (
            result
            for result in results
            if isinstance(result, dict)
            and isinstance(result.get("candidate"), dict)
            and result["candidate"].get("key") == selected_key
        ),
        None,
    )
    if baseline is None:
        raise ValueError("selected candidate is missing from benchmark results")
    rerun_candidate = rerun.get("candidate")
    if not isinstance(rerun_candidate, dict) or rerun_candidate.get("key") != selected_key:
        raise ValueError("rerun candidate does not match the selected candidate")
    if rerun.get("status") != "succeeded":
        raise ValueError("selected candidate rerun did not succeed")
    if rerun.get("dataset_checksum") != baseline.get("dataset_checksum"):
        raise ValueError("rerun dataset checksum does not match the benchmark")
    if rerun.get("dimension") != baseline.get("dimension"):
        raise ValueError("rerun embedding dimension changed")

    tolerance = float(configuration["deterministic_metric_tolerance"])
    deltas = {
        metric: abs(float(baseline[metric]) - float(rerun[metric]))
        for metric in ("hit_rate_at_5", "recall_at_10")
    }
    if any(delta > tolerance for delta in deltas.values()):
        raise ValueError(f"rerun metrics exceed deterministic tolerance: {deltas}")
    return {
        "status": "passed",
        "selected_candidate": selected_key,
        "dimension": rerun["dimension"],
        "metric_deltas": deltas,
        "tolerance": tolerance,
    }


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
