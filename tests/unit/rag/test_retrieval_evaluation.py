from __future__ import annotations

import json

from app.domain.contracts import SearchStatus
from evaluation.run_phase2_retrieval import DEFAULT_DATASET, _aggregate, _percentile


def _case(
    case_id: str,
    *,
    unanswerable: bool = False,
    hit_rate: bool | None = True,
    recall: float | None = 1.0,
    reciprocal_rank: float | None = 1.0,
    latency: float = 10.0,
    missing: tuple[str, ...] = (),
    slices: tuple[str, ...] = ("general",),
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "unanswerable": unanswerable,
        "hit_rate_at_5": None if unanswerable else hit_rate,
        "recall_at_10": None if unanswerable else recall,
        "reciprocal_rank": None if unanswerable else reciprocal_rank,
        "latency_ms": latency,
        "missing_expected_chunk_ids": missing,
        "unanswerable_returned_candidates": 2 if unanswerable else None,
        "slices": slices,
        "status": SearchStatus.SUCCEEDED.value,
    }


def test_latency_percentiles_use_nearest_rank() -> None:
    assert _percentile([10.0, 20.0, 30.0, 40.0], 0.5) == 20.0
    assert _percentile([10.0, 20.0, 30.0, 40.0], 0.95) == 40.0
    assert _percentile([], 0.5) is None


def test_evaluation_metrics_report_macro_scores_misses_slices_and_unanswerable_cases() -> None:
    cases = [
        _case("a", hit_rate=True, recall=1.0, reciprocal_rank=1.0, latency=10.0),
        _case(
            "b",
            hit_rate=False,
            recall=0.5,
            reciprocal_rank=0.5,
            latency=20.0,
            missing=("expected-2",),
            slices=("general", "negation"),
        ),
        _case(
            "u",
            unanswerable=True,
            hit_rate=None,
            recall=None,
            reciprocal_rank=None,
            latency=30.0,
            slices=("unanswerable",),
        ),
    ]

    metrics = _aggregate(cases)

    assert metrics["answerable_case_count"] == 2
    assert metrics["unanswerable_case_count"] == 1
    assert metrics["hit_rate_at_5"] == 0.5
    assert metrics["recall_at_10"] == 0.75
    assert metrics["eligible_mrr"] == 0.75
    assert metrics["missed_expected_chunk_count"] == 1
    assert metrics["cases_with_missed_expected_chunks"] == 1
    assert metrics["unanswerable_returned_candidates"] == 1
    assert metrics["latency_ms"]["p50"] == 20.0
    assert metrics["slices"]["negation"]["recall_at_10"] == 0.5


def test_retrieval_dataset_is_versioned_and_labels_every_case() -> None:
    dataset = json.loads(DEFAULT_DATASET.read_text(encoding="utf-8"))

    assert dataset["schema_version"] == 1
    assert dataset["dataset_id"] == "phase2-sample-acceptance-v1"
    assert len({case["case_id"] for case in dataset["cases"]}) == len(dataset["cases"])
    assert all("unanswerable" in case for case in dataset["cases"])
    assert all(case["expected_chunk_ids"] for case in dataset["cases"] if not case["unanswerable"])
    assert all(not case["expected_chunk_ids"] for case in dataset["cases"] if case["unanswerable"])
