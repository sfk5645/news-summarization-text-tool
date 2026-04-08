"""Turn fetch_news rows into LangChain ``Document`` chunks."""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

_MIN_BODY_CHARS = 40
_CHUNK_SIZE = 1000
_CHUNK_OVERLAP = 150


def rows_to_chunk_documents(rows: list[dict[str, Any]]) -> list[Document]:
    """
    Build chunked documents with metadata for pgvector.

    Metadata is JSON-serializable (strings/ints) for JSONB storage.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=_CHUNK_SIZE,
        chunk_overlap=_CHUNK_OVERLAP,
        length_function=len,
    )
    out: list[Document] = []
    for row in rows:
        guid = (row.get("guid") or row.get("url") or "").strip()
        if not guid:
            continue
        title = (row.get("title") or "").strip()
        url = (row.get("url") or "").strip()
        topic = (row.get("topic") or "").strip() or "UNKNOWN"
        raw_content = str(row.get("content") or "").strip()
        if len(raw_content) < _MIN_BODY_CHARS:
            raw_content = title
        if not raw_content:
            continue
        pub = row.get("published_at")
        pub_s = str(pub) if pub is not None else ""

        base_meta: dict[str, Any] = {
            "article_guid": guid,
            "title": title,
            "url": url,
            "topic": topic,
            "published_at": pub_s,
        }
        for i, chunk in enumerate(splitter.split_text(raw_content)):
            meta = {**base_meta, "chunk_index": i}
            out.append(Document(page_content=chunk, metadata=meta))
    return out
