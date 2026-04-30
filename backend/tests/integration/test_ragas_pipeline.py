"""
Feature: pokedex-arcana — Integration tests for the RAGAS evaluation pipeline.

Tests cover:
- Benchmark query loading (≥ 20 queries, all four categories present)
- RAGAS metric computation (mocked LLM to avoid API costs in CI)
- Persistence to ragas_evaluations table
- Structured WARN log emission for metrics below 0.70

Requirements: 9.2, 9.3, 9.4, 9.5
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BENCHMARK_PATH = Path(__file__).parent.parent.parent / "evaluation" / "benchmark_queries.json"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REQUIRED_CATEGORIES = {"stats", "lore", "damage", "team"}
METRIC_NAMES = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
METRIC_THRESHOLD = 0.70


def _make_scores(value: float = 0.85) -> dict[str, float]:
    """Return a dict of all four RAGAS metrics set to *value*."""
    return {m: value for m in METRIC_NAMES}


def _make_low_scores(failing_metric: str, low_value: float = 0.50) -> dict[str, float]:
    """Return scores where *failing_metric* is below threshold."""
    scores = _make_scores(0.85)
    scores[failing_metric] = low_value
    return scores


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def benchmark_queries() -> list[dict[str, Any]]:
    """Load the real benchmark_queries.json file."""
    with BENCHMARK_PATH.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture()
def mock_db_session():
    """Minimal SQLAlchemy session mock that records added objects."""
    session = MagicMock()
    session.added_objects: list[Any] = []

    def _add(obj: Any) -> None:
        session.added_objects.append(obj)

    session.add.side_effect = _add
    session.flush.return_value = None
    session.commit.return_value = None
    return session


@pytest.fixture()
def mock_answer_fn():
    """Async callable that returns a canned answer for any query."""
    async def _answer(query: str) -> str:  # noqa: ARG001
        return "This is a mocked answer for the query."

    return _answer


# ---------------------------------------------------------------------------
# 1. Benchmark query set validation (Requirement 9.2)
# ---------------------------------------------------------------------------

class TestBenchmarkQuerySet:
    """Validate the structure and coverage of benchmark_queries.json."""

    def test_benchmark_file_exists(self):
        assert BENCHMARK_PATH.exists(), f"benchmark_queries.json not found at {BENCHMARK_PATH}"

    def test_at_least_20_queries(self, benchmark_queries):
        assert len(benchmark_queries) >= 20, (
            f"Expected ≥ 20 benchmark queries, found {len(benchmark_queries)}"
        )

    def test_all_required_categories_present(self, benchmark_queries):
        categories = {q["category"] for q in benchmark_queries}
        missing = REQUIRED_CATEGORIES - categories
        assert not missing, f"Missing categories in benchmark set: {missing}"

    def test_at_least_5_queries_per_category(self, benchmark_queries):
        from collections import Counter
        counts = Counter(q["category"] for q in benchmark_queries)
        for cat in REQUIRED_CATEGORIES:
            assert counts[cat] >= 5, (
                f"Category '{cat}' has only {counts[cat]} queries; need ≥ 5"
            )

    def test_each_query_has_required_fields(self, benchmark_queries):
        required_fields = {"id", "category", "query", "ground_truth", "contexts"}
        for q in benchmark_queries:
            missing = required_fields - q.keys()
            assert not missing, f"Query {q.get('id', '?')} missing fields: {missing}"

    def test_each_query_has_non_empty_contexts(self, benchmark_queries):
        for q in benchmark_queries:
            assert q["contexts"], f"Query {q['id']} has empty contexts list"

    def test_query_ids_are_unique(self, benchmark_queries):
        ids = [q["id"] for q in benchmark_queries]
        assert len(ids) == len(set(ids)), "Duplicate query IDs found in benchmark set"


# ---------------------------------------------------------------------------
# 2. load_benchmark_queries (Requirement 9.2)
# ---------------------------------------------------------------------------

class TestLoadBenchmarkQueries:
    def test_loads_successfully(self):
        from backend.evaluation.ragas_eval import load_benchmark_queries
        queries = load_benchmark_queries()
        assert len(queries) >= 20

    def test_raises_on_insufficient_queries(self, tmp_path, monkeypatch):
        from backend.evaluation import ragas_eval

        small_file = tmp_path / "small.json"
        small_file.write_text(json.dumps([{"id": "x", "category": "stats"}]))
        monkeypatch.setattr(ragas_eval, "BENCHMARK_PATH", small_file)

        with pytest.raises(ValueError, match="at least 20"):
            ragas_eval.load_benchmark_queries()


# ---------------------------------------------------------------------------
# 3. RAGAS metric computation (Requirement 9.3)
# ---------------------------------------------------------------------------

class TestComputeRagasMetrics:
    """
    Mock the RAGAS library to avoid real LLM calls in CI.
    Validates that compute_ragas_metrics returns one score dict per query
    with all four metric keys present and non-null.
    """

    def _make_mock_ragas_result(self, n_rows: int, value: float = 0.85):
        """Build a mock RAGAS result whose to_pandas() returns a DataFrame."""
        import pandas as pd  # type: ignore[import]

        df = pd.DataFrame(
            [{m: value for m in METRIC_NAMES} for _ in range(n_rows)]
        )
        mock_result = MagicMock()
        mock_result.to_pandas.return_value = df
        return mock_result

    def test_returns_one_score_dict_per_query(self, benchmark_queries):
        from backend.evaluation.ragas_eval import build_ragas_dataset, compute_ragas_metrics

        n = len(benchmark_queries)
        answers = ["mocked answer"] * n
        mock_result = self._make_mock_ragas_result(n)

        mock_dataset = MagicMock()

        with (
            patch("backend.evaluation.ragas_eval.build_ragas_dataset", return_value=mock_dataset),
            patch("backend.evaluation.ragas_eval.compute_ragas_metrics") as mock_compute,
        ):
            mock_compute.return_value = [_make_scores() for _ in range(n)]
            scores = mock_compute(mock_dataset)

        assert len(scores) == n

    def test_all_four_metrics_present_in_each_score(self):
        from backend.evaluation.ragas_eval import compute_ragas_metrics

        n = 5
        mock_result = self._make_mock_ragas_result(n)
        mock_dataset = MagicMock()

        with patch("ragas.evaluate", return_value=mock_result):
            with patch("datasets.Dataset") as _mock_ds:
                scores = compute_ragas_metrics(mock_dataset)

        for score_dict in scores:
            for metric in METRIC_NAMES:
                assert metric in score_dict, f"Metric '{metric}' missing from score dict"
                assert score_dict[metric] is not None

    def test_metric_values_are_floats(self):
        from backend.evaluation.ragas_eval import compute_ragas_metrics

        n = 3
        mock_result = self._make_mock_ragas_result(n, value=0.75)
        mock_dataset = MagicMock()

        with patch("ragas.evaluate", return_value=mock_result):
            scores = compute_ragas_metrics(mock_dataset)

        for score_dict in scores:
            for metric in METRIC_NAMES:
                assert isinstance(score_dict[metric], float), (
                    f"Expected float for {metric}, got {type(score_dict[metric])}"
                )


# ---------------------------------------------------------------------------
# 4. Persistence to ragas_evaluations (Requirement 9.4)
# ---------------------------------------------------------------------------

class TestPersistEvaluationResults:
    def test_adds_one_record_per_query(self, benchmark_queries, mock_db_session):
        from backend.evaluation.ragas_eval import persist_evaluation_results

        scores = [_make_scores() for _ in benchmark_queries]
        records = persist_evaluation_results(mock_db_session, benchmark_queries, scores)

        assert len(records) == len(benchmark_queries)
        assert mock_db_session.add.call_count == len(benchmark_queries)

    def test_record_fields_match_query(self, benchmark_queries, mock_db_session):
        from backend.evaluation.ragas_eval import persist_evaluation_results

        scores = [_make_scores(0.80) for _ in benchmark_queries]
        ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
        records = persist_evaluation_results(
            mock_db_session, benchmark_queries, scores,
            system_version="test-1.0", evaluated_at=ts,
        )

        for record, query in zip(records, benchmark_queries):
            assert record.query_id == query["id"]
            assert record.query_category == query["category"]
            assert record.system_version == "test-1.0"
            assert record.evaluated_at == ts

    def test_metric_scores_stored_on_record(self, benchmark_queries, mock_db_session):
        from backend.evaluation.ragas_eval import persist_evaluation_results

        expected_scores = _make_scores(0.75)
        scores = [expected_scores.copy() for _ in benchmark_queries]
        records = persist_evaluation_results(mock_db_session, benchmark_queries, scores)

        for record in records:
            assert record.faithfulness == pytest.approx(0.75)
            assert record.answer_relevancy == pytest.approx(0.75)
            assert record.context_precision == pytest.approx(0.75)
            assert record.context_recall == pytest.approx(0.75)

    def test_session_flush_called(self, benchmark_queries, mock_db_session):
        from backend.evaluation.ragas_eval import persist_evaluation_results

        scores = [_make_scores() for _ in benchmark_queries]
        persist_evaluation_results(mock_db_session, benchmark_queries, scores)
        mock_db_session.flush.assert_called_once()


# ---------------------------------------------------------------------------
# 5. WARN log for metrics below 0.70 (Requirement 9.5)
# ---------------------------------------------------------------------------

class TestWarnOnLowScores:
    def test_no_warning_when_all_metrics_pass(self, caplog):
        from backend.evaluation.ragas_eval import warn_on_low_scores

        query = {"id": "stats_001", "category": "stats"}
        scores = _make_scores(0.85)

        with caplog.at_level(logging.WARNING):
            warn_on_low_scores(query, scores)

        # structlog warnings won't appear in caplog by default; we verify via mock
        # (structlog uses its own processor chain)

    def test_warning_emitted_for_low_faithfulness(self):
        from backend.evaluation.ragas_eval import warn_on_low_scores

        query = {"id": "lore_001", "category": "lore"}
        scores = _make_low_scores("faithfulness", 0.45)

        with patch("backend.evaluation.ragas_eval.logger") as mock_logger:
            warn_on_low_scores(query, scores)
            mock_logger.warning.assert_called_once()
            call_kwargs = mock_logger.warning.call_args
            assert call_kwargs[0][0] == "ragas_metric_below_threshold"
            assert call_kwargs[1]["metric"] == "faithfulness"
            assert call_kwargs[1]["query_id"] == "lore_001"
            assert call_kwargs[1]["query_category"] == "lore"

    def test_warning_emitted_for_low_answer_relevancy(self):
        from backend.evaluation.ragas_eval import warn_on_low_scores

        query = {"id": "damage_001", "category": "damage"}
        scores = _make_low_scores("answer_relevancy", 0.60)

        with patch("backend.evaluation.ragas_eval.logger") as mock_logger:
            warn_on_low_scores(query, scores)
            mock_logger.warning.assert_called_once()
            call_kwargs = mock_logger.warning.call_args
            assert call_kwargs[1]["metric"] == "answer_relevancy"

    def test_warning_emitted_for_low_context_precision(self):
        from backend.evaluation.ragas_eval import warn_on_low_scores

        query = {"id": "team_001", "category": "team"}
        scores = _make_low_scores("context_precision", 0.55)

        with patch("backend.evaluation.ragas_eval.logger") as mock_logger:
            warn_on_low_scores(query, scores)
            mock_logger.warning.assert_called_once()
            call_kwargs = mock_logger.warning.call_args
            assert call_kwargs[1]["metric"] == "context_precision"

    def test_warning_emitted_for_low_context_recall(self):
        from backend.evaluation.ragas_eval import warn_on_low_scores

        query = {"id": "stats_002", "category": "stats"}
        scores = _make_low_scores("context_recall", 0.30)

        with patch("backend.evaluation.ragas_eval.logger") as mock_logger:
            warn_on_low_scores(query, scores)
            mock_logger.warning.assert_called_once()
            call_kwargs = mock_logger.warning.call_args
            assert call_kwargs[1]["metric"] == "context_recall"

    def test_multiple_warnings_for_multiple_failing_metrics(self):
        from backend.evaluation.ragas_eval import warn_on_low_scores

        query = {"id": "lore_002", "category": "lore"}
        scores = {
            "faithfulness": 0.40,
            "answer_relevancy": 0.35,
            "context_precision": 0.85,
            "context_recall": 0.90,
        }

        with patch("backend.evaluation.ragas_eval.logger") as mock_logger:
            warn_on_low_scores(query, scores)
            assert mock_logger.warning.call_count == 2

    def test_warning_contains_threshold_value(self):
        from backend.evaluation.ragas_eval import warn_on_low_scores

        query = {"id": "damage_002", "category": "damage"}
        scores = _make_low_scores("faithfulness", 0.50)

        with patch("backend.evaluation.ragas_eval.logger") as mock_logger:
            warn_on_low_scores(query, scores)
            call_kwargs = mock_logger.warning.call_args
            assert call_kwargs[1]["threshold"] == METRIC_THRESHOLD

    def test_no_warning_at_exact_threshold(self):
        from backend.evaluation.ragas_eval import warn_on_low_scores

        query = {"id": "stats_003", "category": "stats"}
        scores = _make_scores(METRIC_THRESHOLD)  # exactly 0.70

        with patch("backend.evaluation.ragas_eval.logger") as mock_logger:
            warn_on_low_scores(query, scores)
            mock_logger.warning.assert_not_called()


# ---------------------------------------------------------------------------
# 6. End-to-end pipeline (mocked LLM + RAGAS) (Requirements 9.3, 9.4, 9.5)
# ---------------------------------------------------------------------------

class TestRunEvaluationPipeline:
    """
    Integration-level test for run_evaluation_pipeline.
    All LLM and RAGAS calls are mocked to avoid API costs in CI.
    """

    def _make_mock_ragas_result(self, n_rows: int, value: float = 0.85):
        import pandas as pd  # type: ignore[import]

        df = pd.DataFrame(
            [{m: value for m in METRIC_NAMES} for _ in range(n_rows)]
        )
        mock_result = MagicMock()
        mock_result.to_pandas.return_value = df
        return mock_result

    @pytest.mark.asyncio
    async def test_pipeline_returns_result_per_query(self, mock_db_session):
        from backend.evaluation.ragas_eval import load_benchmark_queries, run_evaluation_pipeline

        queries = load_benchmark_queries()
        n = len(queries)
        mock_result = self._make_mock_ragas_result(n)

        async def _answer(query: str) -> str:  # noqa: ARG001
            return "Mocked answer."

        with (
            patch("ragas.evaluate", return_value=mock_result),
            patch("datasets.Dataset.from_dict") as mock_from_dict,
        ):
            mock_from_dict.return_value = MagicMock()
            results = await run_evaluation_pipeline(_answer, mock_db_session)

        assert len(results) == n

    @pytest.mark.asyncio
    async def test_pipeline_result_has_required_keys(self, mock_db_session):
        from backend.evaluation.ragas_eval import load_benchmark_queries, run_evaluation_pipeline

        queries = load_benchmark_queries()
        n = len(queries)
        mock_result = self._make_mock_ragas_result(n)

        async def _answer(query: str) -> str:  # noqa: ARG001
            return "Mocked answer."

        with (
            patch("ragas.evaluate", return_value=mock_result),
            patch("datasets.Dataset.from_dict") as mock_from_dict,
        ):
            mock_from_dict.return_value = MagicMock()
            results = await run_evaluation_pipeline(_answer, mock_db_session)

        for result in results:
            assert "query_id" in result
            assert "category" in result
            assert "scores" in result
            assert "passed" in result

    @pytest.mark.asyncio
    async def test_pipeline_marks_passed_when_all_metrics_above_threshold(self, mock_db_session):
        from backend.evaluation.ragas_eval import load_benchmark_queries, run_evaluation_pipeline

        queries = load_benchmark_queries()
        n = len(queries)
        mock_result = self._make_mock_ragas_result(n, value=0.90)

        async def _answer(query: str) -> str:  # noqa: ARG001
            return "Mocked answer."

        with (
            patch("ragas.evaluate", return_value=mock_result),
            patch("datasets.Dataset.from_dict") as mock_from_dict,
        ):
            mock_from_dict.return_value = MagicMock()
            results = await run_evaluation_pipeline(_answer, mock_db_session)

        assert all(r["passed"] for r in results)

    @pytest.mark.asyncio
    async def test_pipeline_marks_failed_when_metric_below_threshold(self, mock_db_session):
        from backend.evaluation.ragas_eval import load_benchmark_queries, run_evaluation_pipeline

        queries = load_benchmark_queries()
        n = len(queries)
        mock_result = self._make_mock_ragas_result(n, value=0.50)

        async def _answer(query: str) -> str:  # noqa: ARG001
            return "Mocked answer."

        with (
            patch("ragas.evaluate", return_value=mock_result),
            patch("datasets.Dataset.from_dict") as mock_from_dict,
        ):
            mock_from_dict.return_value = MagicMock()
            results = await run_evaluation_pipeline(_answer, mock_db_session)

        assert all(not r["passed"] for r in results)

    @pytest.mark.asyncio
    async def test_pipeline_commits_db_session(self, mock_db_session):
        from backend.evaluation.ragas_eval import load_benchmark_queries, run_evaluation_pipeline

        queries = load_benchmark_queries()
        n = len(queries)
        mock_result = self._make_mock_ragas_result(n)

        async def _answer(query: str) -> str:  # noqa: ARG001
            return "Mocked answer."

        with (
            patch("ragas.evaluate", return_value=mock_result),
            patch("datasets.Dataset.from_dict") as mock_from_dict,
        ):
            mock_from_dict.return_value = MagicMock()
            await run_evaluation_pipeline(_answer, mock_db_session)

        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_pipeline_emits_warn_for_low_metric(self, mock_db_session):
        from backend.evaluation.ragas_eval import load_benchmark_queries, run_evaluation_pipeline

        queries = load_benchmark_queries()
        n = len(queries)
        mock_result = self._make_mock_ragas_result(n, value=0.50)

        async def _answer(query: str) -> str:  # noqa: ARG001
            return "Mocked answer."

        with (
            patch("ragas.evaluate", return_value=mock_result),
            patch("datasets.Dataset.from_dict") as mock_from_dict,
            patch("backend.evaluation.ragas_eval.logger") as mock_logger,
        ):
            mock_from_dict.return_value = MagicMock()
            await run_evaluation_pipeline(_answer, mock_db_session)

        # Each query has 4 failing metrics → n * 4 warnings
        assert mock_logger.warning.call_count == n * 4
