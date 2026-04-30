"""
PDF ingestor: parses PDFs from data/raw/pdfs/ with PyMuPDF (fitz), chunks by
section, embeds with OpenAI text-embedding-3-small, and upserts into ChromaDB
"pdf_guides" collection.

Metadata per chunk: {filename, page_number, section}
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

import structlog

import chromadb

from backend.config import settings
from backend.llm_client import embed_texts
from backend.ingestion.bulbapedia_ingestor import _split_text

log = structlog.get_logger(__name__)

PDF_DIR = Path("data/raw/pdfs")
COLLECTION_NAME = "pdf_guides"
EMBED_BATCH = 50


def _detect_section(text: str, fallback: str = "body") -> str:
    """Heuristically detect a section heading from a block of text."""
    lines = text.strip().splitlines()
    for line in lines[:3]:
        stripped = line.strip()
        # Treat short ALL-CAPS or Title Case lines as section headings
        if stripped and len(stripped) < 80 and (stripped.isupper() or re.match(r"^[A-Z][^.!?]*$", stripped)):
            return stripped
    return fallback


def _extract_pages(pdf_path: Path) -> list[dict]:
    """Return list of {page_number, section, text} dicts from a PDF."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        log.error("pdf_ingestor.pymupdf_missing")
        return []

    pages = []
    try:
        doc = fitz.open(str(pdf_path))
        current_section = "Introduction"
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text("text")
            if not text.strip():
                continue
            section = _detect_section(text, fallback=current_section)
            current_section = section
            pages.append(
                {
                    "page_number": page_num + 1,
                    "section": section,
                    "text": text,
                }
            )
        doc.close()
    except Exception as exc:
        log.error("pdf_ingestor.parse_error", path=str(pdf_path), error=str(exc))

    return pages


async def ingest_pdfs(pdf_dir: Path = PDF_DIR) -> None:
    """Parse all PDFs in pdf_dir and upsert chunks into ChromaDB."""
    if not pdf_dir.exists():
        log.warning("pdf_ingestor.dir_not_found", path=str(pdf_dir))
        return

    pdf_files = list(pdf_dir.glob("*.pdf"))
    if not pdf_files:
        log.warning("pdf_ingestor.no_pdfs", path=str(pdf_dir))
        return

    log.info("pdf_ingestor.start", count=len(pdf_files))

    chroma_client = await chromadb.AsyncHttpClient(
        host=settings.chromadb_host, port=settings.chromadb_port
    )
    collection = await chroma_client.get_or_create_collection(COLLECTION_NAME)

    for pdf_path in pdf_files:
        filename = pdf_path.name
        log.info("pdf_ingestor.processing", filename=filename)

        pages = _extract_pages(pdf_path)
        if not pages:
            log.warning("pdf_ingestor.empty_pdf", filename=filename)
            continue

        all_chunks: list[str] = []
        all_metadatas: list[dict] = []

        for page in pages:
            chunks = _split_text(page["text"])
            for chunk in chunks:
                all_chunks.append(chunk)
                all_metadatas.append(
                    {
                        "filename": filename,
                        "page_number": page["page_number"],
                        "section": page["section"],
                    }
                )

        if not all_chunks:
            continue

        # Embed in batches using local sentence-transformers
        all_embeddings: list[list[float]] = []
        failed = False
        for i in range(0, len(all_chunks), EMBED_BATCH):
            batch = all_chunks[i : i + EMBED_BATCH]
            try:
                embeddings = await embed_texts(batch)
                all_embeddings.extend(embeddings)
            except Exception as exc:
                log.warning(
                    "pdf_ingestor.embed_failed",
                    filename=filename,
                    error=str(exc),
                )
                failed = True
                break

        if failed or len(all_embeddings) != len(all_chunks):
            continue

        ids = [
            hashlib.sha256(f"{filename}:{i}:{chunk[:64]}".encode()).hexdigest()
            for i, chunk in enumerate(all_chunks)
        ]

        await collection.upsert(
            ids=ids,
            embeddings=all_embeddings,
            documents=all_chunks,
            metadatas=all_metadatas,
        )
        log.info("pdf_ingestor.upserted", filename=filename, chunks=len(all_chunks))

    log.info("pdf_ingestor.done")
