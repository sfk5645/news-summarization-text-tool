"""Answer questions using only the latest-indexed article chunks (LangChain + pgvector)."""

import warnings
warnings.filterwarnings("ignore")
from __future__ import annotations

from dataclasses import dataclass

from langchain_community.vectorstores import PGVector
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama

from app.rag.config import (
    NOMIC_EMBED_DIM,
    OLLAMA_BASE_URL,
    OLLAMA_CHAT_MODEL,
    RAG_COLLECTION_NAME,
    get_sqlalchemy_connection_string,
)
from app.rag.embeddings import get_embedding_model


@dataclass
class RAGAnswer:
    answer: str
    sources: list[dict[str, str]]


def _format_context(docs: list) -> str:
    parts: list[str] = []
    for i, d in enumerate(docs, start=1):
        parts.append(f"[{i}] {d.page_content}")
    return "\n\n".join(parts)


def _dedupe_sources(docs: list) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    for d in docs:
        m = d.metadata or {}
        url = (m.get("url") or "").strip()
        key = url or (m.get("article_guid") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "title": (m.get("title") or "")[:500],
                "url": url,
                "topic": (m.get("topic") or "")[:200],
                "published_at": (m.get("published_at") or "")[:80],
            }
        )
    return out


def ask_latest_news(question: str, *, k: int = 8) -> RAGAnswer:
    """
    Retrieve from the current RAG collection (latest ingest only) and answer with ChatOllama.

    Raises:
        RuntimeError: If ``OLLAMA_MODEL`` is unset or the vector store is empty / missing.
    """
    q = (question or "").strip()
    if not q:
        raise ValueError("question must be non-empty")

    chat_model = OLLAMA_CHAT_MODEL
    if not chat_model:
        raise RuntimeError("Set OLLAMA_MODEL in .env for RAG chat (e.g. llama3).")

    emb = get_embedding_model()
    conn = get_sqlalchemy_connection_string()

    store = PGVector(
        connection_string=conn,
        embedding_function=emb,
        collection_name=RAG_COLLECTION_NAME,
        embedding_length=NOMIC_EMBED_DIM,
        use_jsonb=True,
        pre_delete_collection=False,
    )

    docs = store.similarity_search(q, k=k)
    if not docs:
        raise RuntimeError(
            "No indexed chunks found. Run ingest so RAG can index the latest article batch, "
            "and ensure `CREATE EXTENSION vector` is enabled on Postgres."
        )

    context = _format_context(docs)
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You answer using ONLY the context passages below (from the user's latest "
                "news batch). If the context does not contain enough information, say so clearly "
                "and do not invent facts. Be concise.",
            ),
            (
                "human",
                "Context:\n{context}\n\nQuestion: {question}",
            ),
        ]
    )
    llm = ChatOllama(
        model=chat_model,
        base_url=OLLAMA_BASE_URL,
        temperature=0.2,
    )
    chain = prompt | llm
    msg = chain.invoke({"context": context, "question": q})
    answer = (msg.content or "").strip() if hasattr(msg, "content") else str(msg).strip()

    return RAGAnswer(answer=answer, sources=_dedupe_sources([docs[0]]) if docs else [])
