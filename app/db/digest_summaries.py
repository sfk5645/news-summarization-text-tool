"""Persist bullet digests from ``app.summarize.digest``."""

from __future__ import annotations

from typing import Any

import psycopg

from app.db.articles import get_connection

_UPSERT_SQL = """
INSERT INTO digest_summaries (run_at, scope, topic, symbol, bullets)
VALUES (%(run_at)s, %(scope)s, %(topic)s, %(symbol)s, %(bullets)s)
ON CONFLICT (run_at, scope) DO UPDATE SET
    bullets = EXCLUDED.bullets,
    created_at = NOW()
RETURNING id;
"""

_DELETE_SOURCES_SQL = "DELETE FROM digest_summary_sources WHERE digest_summary_id = %s"

_INSERT_SOURCE_SQL = """
INSERT INTO digest_summary_sources (digest_summary_id, article_guid)
VALUES (%s, %s);
"""


def insert_digest_rows(
    rows: list[dict[str, Any]],
    conn: psycopg.Connection | None = None,
) -> int:
    """
    Insert or replace digest rows for a given ``run_at`` + ``scope``.

    Args:
        rows: Each dict has ``run_at``, ``scope``, ``topic``, ``symbol`` (optional),
            ``bullets``, and optional ``source_guids`` (list of ``articles.guid`` used
            for that digest group). Source links are stored in ``digest_summary_sources``
            and replaced on upsert.
        conn: Optional connection; if omitted, opens and closes one.

    Returns:
        Number of digest rows written.
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
            cur = conn.execute(
                _UPSERT_SQL,
                {
                    "run_at": row["run_at"],
                    "scope": row["scope"],
                    "topic": row["topic"],
                    "symbol": row["symbol"],
                    "bullets": row["bullets"],
                },
            )
            one = cur.fetchone()
            if not one:
                raise RuntimeError("UPSERT digest_summaries did not return id")
            digest_id = int(one[0])

            conn.execute(_DELETE_SOURCES_SQL, (digest_id,))

            for guid in row.get("source_guids") or []:
                g = (guid or "").strip()
                if not g:
                    continue
                conn.execute(_INSERT_SOURCE_SQL, (digest_id, g))

            n += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if own:
            conn.close()
    return n
