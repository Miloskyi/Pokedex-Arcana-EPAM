"""BM25 retriever backed by rank_bm25.BM25Okapi.

The index is built in-memory from a list of ScoredDoc objects at ingestion
time and queried at retrieval time.  Scores are normalised to [0, 1] before
being returned so they can be compared / fused with dense scores.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rank_bm25 import BM25Okapi

from backend.rag import ScoredDoc

if TYPE_CHECKING:
    pass


def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, split on whitespace."""
    return re.sub(r"[^\w\s]", " ", text.lower()).split()


class BM25Retriever:
    """Build a BM25 index from a document collection and answer queries."""

    def __init__(self) -> None:
        self._docs: list[ScoredDoc] = []
        self._index: BM25Okapi | None = None

    # ------------------------------------------------------------------
    # Index construction
    # ------------------------------------------------------------------

    def build_index(self, documents: list[ScoredDoc]) -> None:
        """Build (or rebuild) the BM25 index from *documents*.

        Args:
            documents: The full document collection for one ChromaDB
                       collection.  Each document's ``text`` field is
                       tokenised and indexed.
        """
        if not documents:
            self._docs = []
            self._index = None
            return

        self._docs = list(documents)
        tokenised = [_tokenize(doc.text) for doc in self._docs]
        self._index = BM25Okapi(tokenised)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def query(self, text: str, top_k: int = 20) -> list[ScoredDoc]:
        """Return the *top_k* most relevant documents for *text*.

        Scores are normalised to [0, 1] (max-normalisation).  Documents
        with a zero score after normalisation are still returned if they
        fall within the top-k window, but will have ``score = 0.0``.

        Args:
            text:  The query string.
            top_k: Maximum number of results to return.

        Returns:
            A list of :class:`ScoredDoc` objects sorted by descending
            score, length ≤ *top_k*.
        """
        if self._index is None or not self._docs:
            return []

        tokens = _tokenize(text)
        if not tokens:
            return []

        raw_scores: list[float] = self._index.get_scores(tokens).tolist()

        # Normalise to [0, 1]
        max_score = max(raw_scores) if raw_scores else 0.0
        if max_score > 0:
            norm_scores = [s / max_score for s in raw_scores]
        else:
            norm_scores = raw_scores

        # Pair with docs, sort descending, take top_k
        paired = sorted(
            zip(norm_scores, self._docs),
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
            for score, doc in paired
        ]
