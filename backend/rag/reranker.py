"""Cross-encoder reranker using ms-marco-MiniLM-L-6-v2.

The model is lazy-loaded on first use to avoid paying the import cost at
module load time.  ``rerank()`` is a synchronous call because
``sentence_transformers.CrossEncoder.predict()`` is CPU-bound and does not
benefit from ``asyncio``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from backend.rag import ScoredDoc

if TYPE_CHECKING:
    from sentence_transformers import CrossEncoder

_MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker:
    """Rerank a candidate list with a cross-encoder model."""

    def __init__(self) -> None:
        self._model: CrossEncoder | None = None

    # ------------------------------------------------------------------
    # Lazy model loading
    # ------------------------------------------------------------------

    def _get_model(self) -> "CrossEncoder":
        if self._model is None:
            from sentence_transformers import CrossEncoder  # noqa: PLC0415

            self._model = CrossEncoder(_MODEL_NAME)
        return self._model

    # ------------------------------------------------------------------
    # Reranking
    # ------------------------------------------------------------------

    def rerank(
        self,
        query: str,
        candidates: list[ScoredDoc],
        top_k: int = 5,
    ) -> list[ScoredDoc]:
        """Score each candidate against *query* and return the top *top_k*.

        The cross-encoder produces a raw logit for each (query, passage)
        pair.  We use these logits directly as scores (higher = more
        relevant) and sort descending.

        Args:
            query:      The original user query.
            candidates: Candidate passages to rerank (typically top-20
                        from RRF fusion).
            top_k:      Number of passages to return after reranking.

        Returns:
            A list of :class:`ScoredDoc` objects sorted by descending
            cross-encoder score, length ≤ *top_k*.
        """
        if not candidates:
            return []

        model = self._get_model()

        pairs = [(query, doc.text) for doc in candidates]
        scores: list[float] = model.predict(pairs).tolist()

        reranked = sorted(
            zip(scores, candidates),
            key=lambda x: x[0],
            reverse=True,
        )[:top_k]

        return [
            ScoredDoc(
                id=doc.id,
                text=doc.text,
                score=score,
                metadata=doc.metadata,
            )
            for score, doc in reranked
        ]
