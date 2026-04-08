"""
Replace the pgvector RAG index with **only** the articles from the latest ``fetch_news`` batch.

Run ``CREATE EXTENSION vector;`` on Postgres once (superuser) if not already enabled.
LangChain's PGVector will also attempt to create the extension when ``create_extension=True``.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_community.vectorstores import PGVector

from app.rag.chunking import rows_to_chunk_documents
from app.rag.config import (
    NOMIC_EMBED_DIM,
    RAG_COLLECTION_NAME,
    get_sqlalchemy_connection_string,
)
from app.rag.embeddings import get_embedding_model

logger = logging.getLogger(__name__)


def reindex_rag_from_rows(rows: list[dict[str, Any]]) -> int:
    """
    Drop the RAG collection (if any) and rebuild it from ``rows`` only.

    This enforces "questions only on the latest ingest batch": older articles are not
    in the vector store until the next fetch reindexes.

    Returns:
        Number of chunks stored (0 if nothing to index).
    """
    docs = rows_to_chunk_documents(rows)
    conn = get_sqlalchemy_connection_string()
    emb = get_embedding_model()

    if not docs:
        _clear_collection(conn, emb)
        logger.info("RAG: no chunks built from batch; cleared collection %s", RAG_COLLECTION_NAME)
        return 0

    PGVector.from_documents(
        documents=docs,
        embedding=emb,
        collection_name=RAG_COLLECTION_NAME,
        connection_string=conn,
        pre_delete_collection=True,
        use_jsonb=True,
        embedding_length=NOMIC_EMBED_DIM,
    )
    logger.info(
        "RAG: indexed %s chunks from %s articles into collection %s",
        len(docs),
        len(rows),
        RAG_COLLECTION_NAME,
    )
    return len(docs)


def _clear_collection(connection_string: str, emb: Any) -> None:
    """Remove all vectors for our collection when the new batch produced no chunks."""
    store = PGVector(
        connection_string=connection_string,
        embedding_function=emb,
        collection_name=RAG_COLLECTION_NAME,
        embedding_length=NOMIC_EMBED_DIM,
        use_jsonb=True,
        pre_delete_collection=False,
    )
    store.delete_collection()
