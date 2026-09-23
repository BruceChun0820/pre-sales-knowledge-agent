from __future__ import annotations

import pytest

from app.rag.benchmark import (
    EvaluationQuery,
    evaluate_retrieval,
    percentile,
    select_candidate,
    verify_selected_rerun,
)


def test_retrieval_metrics_rank_expected_chunks() -> None:
    queries = (
        EvaluationQuery(query_id="q1", text="alpha", relevant_chunk_ids=("c1",)),
        EvaluationQuery(query_id="q2", text="beta", relevant_chunk_ids=("c2",)),
    )

    metrics = evaluate_retrieval(
        chunk_ids=("c1", "c2"),
        document_vectors=((1.0, 0.0), (0.0, 1.0)),
        queries=queries,
        query_vectors=((1.0, 0.0), (0.0, 1.0)),
    )

    assert metrics["hit_rate_at_5"] == 1.0
    assert metrics["recall_at_10"] == 1.0
    assert metrics["per_query"][0]["top_chunk_ids"][0] == "c1"
    assert percentile([1.0, 3.0], 0.5) == 2.0


def test_selection_prefers_lower_cpu_cost_when_quality_is_within_tolerance() -> None:
    results = [
        {
            "status": "succeeded",
            "candidate": {"key": "small"},
            "hit_rate_at_5": 1.0,
            "recall_at_10": 1.0,
            "query_latency_p95_ms": 10.0,
            "peak_rss_mb": 1000.0,
            "estimated_index_size_bytes_float32": 100,
        },
        {
            "status": "succeeded",
            "candidate": {"key": "large"},
            "hit_rate_at_5": 1.0,
            "recall_at_10": 1.0,
            "query_latency_p95_ms": 30.0,
            "peak_rss_mb": 2000.0,
            "estimated_index_size_bytes_float32": 300,
        },
    ]

    decision = select_candidate(results, tolerance=0.01)

    assert decision["status"] == "selected"
    assert decision["selected_candidate"] == "small"


def test_selection_blocks_when_a_candidate_fails() -> None:
    decision = select_candidate(
        [{"status": "failed", "candidate": {"key": "small"}}],
        tolerance=0.01,
    )

    assert decision["status"] == "blocked"
    assert decision["selected_candidate"] is None


def test_selected_rerun_verification_checks_dimension_and_metric_tolerance() -> None:
    candidate = {"key": "small"}
    baseline = {
        "candidate": candidate,
        "dataset_checksum": "abc",
        "dimension": 384,
        "hit_rate_at_5": 1.0,
        "recall_at_10": 1.0,
    }
    benchmark = {
        "decision": {"status": "selected", "selected_candidate": "small"},
        "configuration": {"deterministic_metric_tolerance": 0.01},
        "results": [baseline],
    }
    rerun = {**baseline, "status": "succeeded", "hit_rate_at_5": 0.995}

    evidence = verify_selected_rerun(benchmark, rerun)

    assert evidence["status"] == "passed"
    assert evidence["dimension"] == 384
    assert evidence["metric_deltas"]["hit_rate_at_5"] == pytest.approx(0.005)
