"""
Feature: pokedex-arcana — RAGAS evaluation pipeline.

Loads benchmark queries, runs RAGAS metrics, persists results to PostgreSQL,
and emits structured WARN logs for any metric below the 0.70 threshold.

Requirements: 9.2, 9.3, 9.4, 9.5
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)

BENCHMARK_PATH = Path(__file__).parent / "benchmark_queries.json"
METRIC_THRESHOLD = 0.70
SYSTEM_VERSION = "0.1.0"

# Metric names as returned by RAGAS
METRIC_NAMES = [
    "faithfulness",
    "answer_relevancy",
    "context_precision",
    "context_recall",
]


def load_benchmark_queries() -> list[dict[str, Any]]:
    """Load annotated benchmark queries from the JSON file."""
    with BENCHMARK_PATH.open("r", encoding="utf-8") as fh:
        queries = json.load(fh)
    if len(queries) < 20:
        raise ValueError(
            f"Benchmark set must contain at least 20 queries, found {len(queries)}"
        )
    return queries


def build_ragas_dataset(
    queries: list[dict[str, Any]],
    answers: list[str],
) -> "Dataset":  # type: ignore[name-defined]
    """
    Build a RAGAS-compatible HuggingFace Dataset from benchmark queries and
    generated answers.

    Each row contains: question, answer, contexts, ground_truth.
    """
    from datasets import Dataset  # type: ignore[import]

    rows = {
        "question": [q["query"] for q in queries],
        "answer": answers,
        "contexts": [q["contexts"] for q in queries],
        "ground_truth": [q["ground_truth"] for q in queries],
    }
    return Dataset.from_dict(rows)


def compute_ragas_metrics(dataset: "Dataset") -> list[dict[str, float]]:  # type: ignore[name-defined]
    """
    Run RAGAS evaluation on the dataset and return per-row metric scores.

    Returns a list of dicts, one per query, with keys:
    faithfulness, answer_relevancy, context_precision, context_recall.
    """
    from ragas import evaluate  # type: ignore[import]
    from ragas.metrics import (  # type: ignore[import]
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
    )
    # result.to_pandas() returns a DataFrame; convert to list of dicts
    df = result.to_pandas()
    return df[METRIC_NAMES].to_dict(orient="records")


def warn_on_low_scores(
    query: dict[str, Any],
    scores: dict[str, float],
) -> None:
    """Emit a structured WARN log for any metric below METRIC_THRESHOLD."""
    for metric_name in METRIC_NAMES:
        score = scores.get(metric_name)
        if score is not None and score < METRIC_THRESHOLD:
            logger.warning(
                "ragas_metric_below_threshold",
                query_id=query["id"],
                query_category=query["category"],
                metric=metric_name,
                score=round(score, 4),
                threshold=METRIC_THRESHOLD,
            )


def persist_evaluation_results(
    session: Any,
    queries: list[dict[str, Any]],
    scores_per_query: list[dict[str, float]],
    system_version: str = SYSTEM_VERSION,
    evaluated_at: Optional[datetime] = None,
) -> list[Any]:
    """
    Persist RAGAS evaluation results to the ragas_evaluations table.

    Parameters
    ----------
    session:
        SQLAlchemy Session (sync or async-compatible).
    queries:
        The benchmark query dicts (must include 'id' and 'category').
    scores_per_query:
        Per-query metric scores in the same order as *queries*.
    system_version:
        Version tag stored alongside the results.
    evaluated_at:
        Timestamp override; defaults to UTC now.

    Returns
    -------
    list of RagasEvaluation ORM instances that were added to the session.
    """
    from backend.models.ragas import RagasEvaluation  # noqa: PLC0415

    ts = evaluated_at or datetime.now(tz=timezone.utc)
    records: list[RagasEvaluation] = []

    for query, scores in zip(queries, scores_per_query):
        record = RagasEvaluation(
            evaluated_at=ts,
            system_version=system_version,
            query_id=query["id"],
            query_category=query["category"],
            faithfulness=scores.get("faithfulness"),
            answer_relevancy=scores.get("answer_relevancy"),
            context_precision=scores.get("context_precision"),
            context_recall=scores.get("context_recall"),
        )
        session.add(record)
        records.append(record)

    session.flush()
    return records


async def run_evaluation_pipeline(
    answer_fn: Any,
    db_session: Any,
    system_version: str = SYSTEM_VERSION,
) -> list[dict[str, Any]]:
    """
    End-to-end RAGAS evaluation pipeline.

    Parameters
    ----------
    answer_fn:
        Async callable ``answer_fn(query: str) -> str`` that generates an
        answer for a given query string (wraps the real agent or a mock).
    db_session:
        SQLAlchemy session used to persist results.
    system_version:
        Version tag for this evaluation run.

    Returns
    -------
    List of result dicts with keys: query_id, category, scores, passed.
    """
    queries = load_benchmark_queries()

    # Generate answers for all queries
    answers: list[str] = []
    for q in queries:
        answer = await answer_fn(q["query"])
        answers.append(answer)

    dataset = build_ragas_dataset(queries, answers)
    scores_per_query = compute_ragas_metrics(dataset)

    # Warn on low scores and build result summary
    results: list[dict[str, Any]] = []
    for query, scores in zip(queries, scores_per_query):
        warn_on_low_scores(query, scores)
        passed = all(
            scores.get(m, 0.0) >= METRIC_THRESHOLD for m in METRIC_NAMES
        )
        results.append(
            {
                "query_id": query["id"],
                "category": query["category"],
                "scores": scores,
                "passed": passed,
            }
        )

    persist_evaluation_results(
        db_session,
        queries,
        scores_per_query,
        system_version=system_version,
    )
    db_session.commit()

    return results
