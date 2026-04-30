"""Dense retriever: ChromaDB + local sentence-transformers embeddings.

Uses ``all-MiniLM-L6-v2`` (384-dim) via sentence-transformers running
fully locally — no API key or internet connection required.
"""
from __future__ import annotations

import chromadb

from backend.config import settings
from backend.llm_client import embed_text
from backend.rag import ScoredDoc

# Embedding dimension for all-MiniLM-L6-v2
_EMBED_DIM = 384


class DenseRetriever:
    """Async dense retriever backed by ChromaDB and local embeddings."""

    def __init__(self, collection_name: str) -> None:
        self._collection_name = collection_name
        self._chroma_client: chromadb.AsyncHttpClient | None = None

    async def _get_chroma_client(self) -> chromadb.AsyncHttpClient:
        if self._chroma_client is None:
            self._chroma_client = await chromadb.AsyncHttpClient(
                host=settings.chromadb_host,
                port=settings.chromadb_port,
            )
        return self._chroma_client

    async def query(self, text: str, top_k: int = 20) -> list[ScoredDoc]:
        """Embed *text* locally and return the *top_k* nearest neighbours from ChromaDB.

        ChromaDB returns cosine distances in [0, 2]; we convert to a
        similarity score in [0, 1] via ``score = 1 - distance / 2``.
        """
        embedding = await embed_text(text)

        chroma = await self._get_chroma_client()
        try:
            collection = await chroma.get_collection(self._collection_name)
        except Exception:
            # Collection doesn't exist yet (ingestion not run)
            return []

        try:
            results = await collection.query(
                query_embeddings=[embedding],
                n_results=min(top_k, 10),   # cap to avoid empty-collection errors
                include=["documents", "metadatas", "distances"],
            )
        except Exception:
            return []

        docs: list[ScoredDoc] = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        for doc_id, doc_text, meta, dist in zip(ids, documents, metadatas, distances):
            score = 1.0 - dist / 2.0
            docs.append(
                ScoredDoc(
                    id=str(doc_id),
                    text=doc_text or "",
                    score=score,
                    metadata=meta or {},
                )
            )

        docs.sort(key=lambda d: d.score, reverse=True)
        return docs
