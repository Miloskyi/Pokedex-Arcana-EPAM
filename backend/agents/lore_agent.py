"""Lore Agent — retrieves Pokémon lore via the RAG pipeline and generates
a grounded answer using the local LLM.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from backend.llm_client import chat_complete
from backend.observability.tracing import trace_agent
from backend.rag import ScoredDoc
from backend.rag.pipeline import RAGPipeline

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class Citation:
    collection: str
    document_id: str
    passage: str
    source_url: Optional[str] = None


@dataclass
class LoreResult:
    answer: str
    citations: list[Citation]
    no_context_found: bool = False


# ---------------------------------------------------------------------------
# Prompts — kept short to reduce LLM latency
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are Pokédex Arcana, a Pokémon expert. "
    "Answer concisely using ONLY the provided context. "
    "Respond in the same language as the question. "
    "If context is insufficient, say so briefly."
)

_NO_CONTEXT_ANSWER = (
    "No tengo información suficiente en mi base de conocimiento para responder esto. "
    "/ I don't have enough information in my knowledge base to answer this."
)


class LoreAgent:
    """Retrieves lore passages and generates a grounded answer."""

    def _build_context(self, docs: list[ScoredDoc]) -> str:
        # Use only top 3 docs and truncate each to 300 chars to reduce LLM input
        parts: list[str] = []
        for i, doc in enumerate(docs[:3], start=1):
            text = doc.text[:300].strip()
            parts.append(f"[{i}] {text}")
        return "\n\n".join(parts)

    def _build_citations(self, docs: list[ScoredDoc], collection_name: str) -> list[Citation]:
        citations: list[Citation] = []
        for doc in docs[:3]:
            meta = doc.metadata or {}
            source_url = meta.get("url") or meta.get("source_url")
            citations.append(
                Citation(
                    collection=meta.get("collection", collection_name),
                    document_id=doc.id,
                    passage=doc.text[:200],
                    source_url=source_url,
                )
            )
        return citations

    @trace_agent("lore")
    async def run(
        self,
        query: str,
        collection_name: str = "bulbapedia",
    ) -> LoreResult:
        """Retrieve lore passages and generate a grounded answer.

        Uses top-3 passages (truncated) to keep LLM input small and fast.
        """
        pipeline = RAGPipeline(collection_name)

        try:
            docs = await pipeline.query(query, top_k=3)
        except Exception:
            docs = []

        # Also try pokedex_entries collection if bulbapedia returns nothing
        if not docs and collection_name == "bulbapedia":
            try:
                pipeline2 = RAGPipeline("pokedex_entries")
                docs = await pipeline2.query(query, top_k=3)
                collection_name = "pokedex_entries"
            except Exception:
                docs = []

        if not docs:
            return LoreResult(
                answer=_NO_CONTEXT_ANSWER,
                citations=[],
                no_context_found=True,
            )

        context = self._build_context(docs)
        citations = self._build_citations(docs, collection_name)

        user_message = f"Context:\n{context}\n\nQuestion: {query}\n\nAnswer briefly (2-4 sentences):"

        try:
            answer = await chat_complete(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.1,
                max_tokens=256,   # Reduced from 512 to speed up llama3.1:8b
            )
        except Exception as exc:
            # If LLM fails, return the raw context as the answer
            answer = f"Based on available data: {docs[0].text[:400]}"

        return LoreResult(
            answer=answer or _NO_CONTEXT_ANSWER,
            citations=citations,
            no_context_found=False,
        )
