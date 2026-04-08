"""Ollama embedding model for LangChain (nomic-embed-text)."""

from __future__ import annotations

from langchain_ollama import OllamaEmbeddings

from app.rag.config import OLLAMA_BASE_URL, OLLAMA_EMBED_MODEL


def get_embedding_model() -> OllamaEmbeddings:
    return OllamaEmbeddings(
        model=OLLAMA_EMBED_MODEL,
        base_url=OLLAMA_BASE_URL,
    )
