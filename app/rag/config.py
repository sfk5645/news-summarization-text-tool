"""RAG configuration from environment."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# LangChain PGVector collection: replaced on each ingest with only that fetch's articles.
RAG_COLLECTION_NAME = os.getenv("RAG_COLLECTION_NAME", "news_latest_batch")

OLLAMA_BASE_URL = (os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip("/")
OLLAMA_CHAT_MODEL = (os.getenv("OLLAMA_MODEL") or "").strip()
OLLAMA_EMBED_MODEL = (os.getenv("OLLAMA_EMBED_MODEL") or "nomic-embed-text").strip()

# nomic-embed-text via Ollama uses 768 dimensions
NOMIC_EMBED_DIM = 768


def get_sqlalchemy_connection_string() -> str:
    """SQLAlchemy URL for psycopg3 (matches ``DATABASE_URL``)."""
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Required for pgvector RAG (same DB as articles)."
        )
    for prefix in ("postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url
