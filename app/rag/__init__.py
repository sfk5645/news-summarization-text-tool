"""RAG over the latest ingest batch: LangChain + pgvector + Ollama (nomic-embed-text)."""

from app.rag.index import reindex_rag_from_rows
from app.rag.query import RAGAnswer, ask_latest_news

__all__ = ["RAGAnswer", "ask_latest_news", "reindex_rag_from_rows"]
