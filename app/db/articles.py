"""Postgres persistence for news rows from ``app.news.news.fetch_news``."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from dotenv import load_dotenv

load_dotenv()

_UPSERT_SQL = """
INSERT INTO articles (
    guid, topic, title, url, published_at, content, feed_url,
    symbol, pct_change_day, last_price, previous_close, currency
) VALUES (
    %(guid)s, %(topic)s, %(title)s, %(url)s, %(published_at)s, %(content)s, %(feed_url)s,
    %(symbol)s, %(pct_change_day)s, %(last_price)s, %(previous_close)s, %(currency)s
)
ON CONFLICT (guid) DO UPDATE SET
    topic = EXCLUDED.topic,
    title = EXCLUDED.title,
    url = EXCLUDED.url,
    published_at = EXCLUDED.published_at,
    content = EXCLUDED.content,
    feed_url = EXCLUDED.feed_url,
    symbol = EXCLUDED.symbol,
    pct_change_day = EXCLUDED.pct_change_day,
    last_price = EXCLUDED.last_price,
    previous_close = EXCLUDED.previous_close,
    currency = EXCLUDED.currency,
    first_seen_at = articles.first_seen_at,
    updated_at = NOW();
"""


def get_connection() -> psycopg.Connection:
    """
    Open a connection using ``DATABASE_URL`` from the environment.

    Returns:
        An open ``psycopg.Connection``.

    Raises:
        RuntimeError: If ``DATABASE_URL`` is missing.
    """
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Add it to .env, e.g. "
            "postgresql://USER@localhost:5432/news_app"
        )
    return psycopg.connect(url)


def _schema_path() -> Path:
    return Path(__file__).resolve().parents[2] / "sql" / "schema.sql"


def init_schema(conn: psycopg.Connection | None = None) -> None:
    """
    Create tables and indexes from ``sql/schema.sql`` if they do not exist.

    Args:
        conn: Existing connection, or ``None`` to open and close one.
    """
    sql = _schema_path().read_text(encoding="utf-8")
    own = conn is None
    if own:
        conn = get_connection()
    try:
        for raw in sql.split(";"):
            stmt = raw.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
    finally:
        if own and conn is not None:
            conn.close()


def _parse_published_at(value: str | None) -> datetime | None:
    if not value or not str(value).strip():
        return None
    s = str(value).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _row_to_params(row: dict[str, Any]) -> dict[str, Any]:
    guid = (row.get("guid") or "").strip() or None
    url = (row.get("url") or "").strip()
    if not guid:
        guid = url or None
    if not guid:
        raise ValueError("Row has no guid and no url; cannot upsert")

    title = (row.get("title") or "").strip()
    content = row.get("content")
    if content is None:
        content = ""
    elif not isinstance(content, str):
        content = str(content)

    return {
        "guid": guid,
        "topic": (row.get("topic") or "").strip() or "UNKNOWN",
        "title": title or "(no title)",
        "url": url or "about:blank",
        "published_at": _parse_published_at(row.get("published_at")),
        "content": content,
        "feed_url": (row.get("feed_url") or "").strip() or "unknown",
        "symbol": row.get("symbol"),
        "pct_change_day": row.get("pct_change_day"),
        "last_price": row.get("last_price"),
        "previous_close": row.get("previous_close"),
        "currency": row.get("currency"),
    }


def upsert_articles(
    rows: list[dict[str, Any]],
    conn: psycopg.Connection | None = None,
) -> int:
    """
    Upsert news rows into ``articles`` (match on ``guid``).

    Args:
        rows: Dicts in the shape produced by ``fetch_news()``.
        conn: Optional open connection; if ``None``, one is opened and closed.

    Returns:
        Number of rows processed.

    Raises:
        RuntimeError: On DB errors after rollback.
    """
    if not rows:
        return 0

    own = conn is None
    if own:
        conn = get_connection()
    assert conn is not None
    n = 0
    try:
        for row in rows:
            params = _row_to_params(row)
            conn.execute(_UPSERT_SQL, params)
            n += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()
    return n


def fetch_and_store_news(
    conn: psycopg.Connection | None = None,
    *,
    summarize_digest: bool = False,
    print_digest: bool = False,
    index_rag: bool = True,
    telegram_digest: bool = False,
    **fetch_kwargs: Any,
) -> int:
    """
    Run ``fetch_news(**fetch_kwargs)`` and upsert all rows.

    Args:
        conn: Optional DB connection for upserts.
        summarize_digest: If True, after upserting, call Ollama and write rows to
            ``digest_summaries`` for this batch (separate DB connection for inserts).
        print_digest: If True (and ``summarize_digest``), print each digest to stdout.
        telegram_digest: If True (and ``summarize_digest``), send the digest PDF to every
            configured Telegram chat (``TELEGRAM_BOT_TOKEN`` plus ``TELEGRAM_CHAT_ID`` and/or
            ``TELEGRAM_DIGEST_CHAT_IDS``).
        index_rag: If True, replace the pgvector index so RAG queries only see this fetch's
            articles (LangChain PGVector + ``nomic-embed-text``). Requires ``CREATE EXTENSION
            vector`` on Postgres and LangChain deps installed.
        **fetch_kwargs: Passed to ``app.news.news.fetch_news``.

    Returns:
        Number of rows upserted.
    """
    from app.news.news import fetch_news

    rows = fetch_news(**fetch_kwargs)
    n = upsert_articles(rows, conn=conn)
    digest_rows: list[dict[str, Any]] = []
    if summarize_digest and rows:
        from app.summarize.digest import run_digest_for_rows

        _, digest_rows = run_digest_for_rows(rows, print_digest=print_digest)
    if telegram_digest and digest_rows:
        from app.telegram.notify import send_digest_pdf

        send_digest_pdf(digest_rows)
    if index_rag:
        from app.rag.index import reindex_rag_from_rows

        reindex_rag_from_rows(rows)
    return n
