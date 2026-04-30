"""Hybrid RAG pipeline: BM25 + dense retrieval → RRF fusion → reranker.

Flow
----
1. BM25Retriever.query(text, top_k=20)   → up to 20 candidates
2. DenseRetriever.query(text, top_k=20)  → up to 20 candidates
3. Reciprocal Rank Fusion (k=60)         → merged ranked list
4. Take top-20 from RRF result
5. CrossEncoderReranker.rerank(...)      → top-5 passages

``query_with_expansion`` additionally generates 2 alternative queries via
the OpenAI chat API, runs the full pipeline for each, and merges the
results with a final RRF pass before reranking.
"""
from __future__ import annotations

from collections import defaultdict

from backend.llm_client import chat_complete
from backend.rag import ScoredDoc
from backend.rag.bm25_retriever import BM25Retriever
from backend.rag.dense_retriever import DenseRetriever
from backend.rag.reranker import CrossEncoderReranker

_RRF_K = 60
_RETRIEVER_TOP_K = 20
_RERANKER_TOP_K = 5
_FUSION_TOP_K = 20


def _rrf_fusion(ranked_lists: list[list[ScoredDoc]], k: int = _RRF_K) -> list[ScoredDoc]:
    """Merge multiple ranked lists using Reciprocal Rank Fusion.

    RRF score for document d:
        score(d) = Σ_i  1 / (k + rank_i(d))

    where rank_i is 1-based.  Documents not present in a list are simply
    not counted for that list (they receive no contribution from it).

    Args:
        ranked_lists: Each inner list is a ranked list of ScoredDoc
                      objects (index 0 = rank 1).
        k:            RRF smoothing constant (default 60).

    Returns:
        A single list of ScoredDoc objects sorted by descending RRF
        score.  The ``score`` field is set to the RRF score.  The
        ``text`` and ``metadata`` are taken from the first occurrence of
        each document id across the ranked lists.
    """
    rrf_scores: dict[str, float] = defaultdict(float)
    doc_store: dict[str, ScoredDoc] = {}

    for ranked in ranked_lists:
        for rank, doc in enumerate(ranked, start=1):
            rrf_scores[doc.id] += 1.0 / (k + rank)
            if doc.id not in doc_store:
                doc_store[doc.id] = doc

    merged = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return [
        ScoredDoc(
            id=doc_id,
            text=doc_store[doc_id].text,
            score=score,
            metadata=doc_store[doc_id].metadata,
        )
        for doc_id, score in merged
    ]


class RAGPipeline:
    """Hybrid retrieval pipeline for a single ChromaDB collection."""

    def __init__(self, collection_name: str) -> None:
        self._collection_name = collection_name
        self._bm25 = BM25Retriever()
        self._dense = DenseRetriever(collection_name)
        self._reranker = CrossEncoderReranker()

    async def _generate_alternative_queries(self, text: str, n: int = 2) -> list[str]:
        """Use the local LLM to produce *n* alternative phrasings of *text*."""
        prompt = (
            f"Generate {n} alternative search queries for the following question. "
            "Return only the queries, one per line, with no numbering or extra text.\n\n"
            f"Original query: {text}"
        )
        try:
            raw = await chat_complete(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=200,
            )
            alternatives = [line.strip() for line in raw.splitlines() if line.strip()]
            return alternatives[:n]
        except Exception:
            return []

    async def _retrieve_and_fuse(self, text: str) -> list[ScoredDoc]:
        """Run BM25 + dense retrieval and fuse with RRF."""
        bm25_results = self._bm25.query(text, top_k=_RETRIEVER_TOP_K)
        dense_results = await self._dense.query(text, top_k=_RETRIEVER_TOP_K)
        fused = _rrf_fusion([bm25_results, dense_results])
        return fused[:_FUSION_TOP_K]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_bm25_index(self, documents: list[ScoredDoc]) -> None:
        """Rebuild the BM25 index from *documents* (call after ingestion)."""
        self._bm25.build_index(documents)

    async def query(self, text: str, top_k: int = _RERANKER_TOP_K) -> list[ScoredDoc]:
        """Run the full hybrid pipeline for a single query.

        Steps:
        1. BM25 top-20 + dense top-20
        2. RRF fusion → top-20
        3. Cross-encoder reranker → top-*top_k*

        Args:
            text:   The user query.
            top_k:  Number of passages to return (default 5).

        Returns:
            A list of :class:`ScoredDoc` objects, length ≤ *top_k*.
        """
        candidates = await self._retrieve_and_fuse(text)
        return self._reranker.rerank(text, candidates, top_k=top_k)

    async def query_with_expansion(
        self, text: str, top_k: int = _RERANKER_TOP_K
    ) -> list[ScoredDoc]:
        """Hybrid retrieval with LLM query expansion.

        Generates 2 alternative queries, runs the full retrieval pipeline
        for the original query and each alternative, then merges all
        candidate lists with a final RRF pass before reranking.

        Args:
            text:   The original user query.
            top_k:  Number of passages to return (default 5).

        Returns:
            A list of :class:`ScoredDoc` objects, length ≤ *top_k*.
        """
        alternatives = await self._generate_alternative_queries(text, n=2)
        all_queries = [text] + alternatives

        all_candidate_lists: list[list[ScoredDoc]] = []
        for q in all_queries:
            candidates = await self._retrieve_and_fuse(q)
            all_candidate_lists.append(candidates)

        merged = _rrf_fusion(all_candidate_lists)
        top_candidates = merged[:_FUSION_TOP_K]
        return self._reranker.rerank(text, top_candidates, top_k=top_k)
