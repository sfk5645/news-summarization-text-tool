"""Build per-topic / per-symbol bullet digests from a fetch_news batch via Ollama."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from app.db.digest_summaries import insert_digest_rows
from app.news.news import FINANCE_TOPIC
from app.summarize.ollama import ollama_chat

# Batch call (finance symbols only): two lines, trading + news / no-news note.
_SYSTEM_FINANCE_SYMBOL = (
    "Summarize into plain bullets only. Output exactly 2 lines the user asks for.\n"
    "Each line: '- ' then one sentence, plain text. No * or • characters. "
    "Do not wrap the whole line in quotation marks. Do not repeat or explain these rules.\n"
    "Facts only from the user message. No preamble or title before the first '-'."
)

# One Ollama call per article (all topics except finance-with-symbol) — guarantees 1 bullet per article.
_SYSTEM_SINGLE_ARTICLE = (
    "Write exactly one English sentence summarizing only the article the user pasted. "
    "Use only information from that article. "
    "Do not start with '-', '*', or a bullet. Do not write a title or preamble — only the sentence."
)

_FINANCE_NEWS_FEED = "finance:portfolio:news"

# ~5 articles per topic in normal ingest; allow a little headroom.
_MAX_ARTICLES_PER_GROUP = 8
# Longer excerpts for RAG-style source text (watch total context vs your Ollama model).
_MAX_CHARS_PER_ARTICLE = 8000

_MAX_BULLETS_FINANCE_SYMBOL = 2

_JUNK_SUBSTR = (
    "careful news editor",
    "entire reply",
    "only the bullet list",
    "nothing else",
    "markdown bullet",
    "must be only",
    "your entire reply",
)


def _truncate(s: str, max_len: int) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


def _stable_article_guid(row: dict[str, Any]) -> str | None:
    """Match ``app.db.articles._row_to_params`` so links align with ``articles.guid``."""
    guid = (row.get("guid") or "").strip() or None
    if not guid:
        guid = (row.get("url") or "").strip() or None
    return guid


def _source_guids(g_rows: list[dict[str, Any]]) -> list[str]:
    """Ordered unique guids for junction table (same keys as stored ``articles`` rows)."""
    seen: set[str] = set()
    out: list[str] = []
    for row in g_rows:
        g = _stable_article_guid(row)
        if g and g not in seen:
            seen.add(g)
            out.append(g)
    return out


def _scope_key(topic: str, symbol: str | None) -> str:
    if topic != FINANCE_TOPIC:
        return topic
    if symbol and str(symbol).strip():
        return f"{topic}:{str(symbol).strip().upper()}"
    return f"{topic}:market"


def _group_rows(rows: list[dict[str, Any]]) -> dict[tuple[str, str | None], list[dict[str, Any]]]:
    """Map (topic, symbol) -> rows. FINANCE uses symbol None for market RSS; else per ticker."""
    groups: dict[tuple[str, str | None], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        topic = (row.get("topic") or "UNKNOWN").strip() or "UNKNOWN"
        if topic != FINANCE_TOPIC:
            groups[(topic, None)].append(row)
            continue
        sym = row.get("symbol")
        if sym is not None and str(sym).strip():
            groups[(FINANCE_TOPIC, str(sym).strip().upper())].append(row)
        else:
            groups[(FINANCE_TOPIC, None)].append(row)
    return groups


def _article_count(rows: list[dict[str, Any]]) -> int:
    """How many articles are in this digest group (capped)."""
    return min(len(rows), _MAX_ARTICLES_PER_GROUP)


def _format_excerpt_block(row: dict[str, Any]) -> str:
    title = (row.get("title") or "").strip()
    url = (row.get("url") or "").strip()
    pub = (row.get("published_at") or "").strip()
    body = _truncate(str(row.get("content") or ""), _MAX_CHARS_PER_ARTICLE)
    feed = (row.get("feed_url") or "").strip()
    lines = [
        f"Title: {title}",
        f"URL: {url}",
        f"Published: {pub or 'unknown'}",
        f"Feed: {feed}",
        "Excerpt:",
        body,
    ]
    return "\n".join(lines)


def _is_junk_bullet_body(body: str) -> bool:
    low = body.lower()
    return any(s in low for s in _JUNK_SUBSTR)


def _clean_bullet_body(rest: str) -> str:
    """Normalize body after '- ': drop stray •, unwrap outer ASCII/smart quotes once."""
    s = rest.strip()
    s = re.sub(r"^[•·▪]+\s*", "", s)
    if len(s) >= 2:
        if s[0] in '"\u201c' and s[-1] in '"\u201d':
            s = s[1:-1].strip()
    s = re.sub(r"\s*:\s*$", "", s)
    return s.strip()


def _fallback_one_line(row: dict[str, Any]) -> str:
    t = (row.get("title") or "").strip()
    return t if t else "(No summary available.)"


def _squeeze_single_sentence(raw: str, row: dict[str, Any]) -> str:
    """First line only, strip list markers, junk-check, length cap; else title fallback."""
    s = (raw or "").strip()
    if not s:
        return _fallback_one_line(row)
    s = s.splitlines()[0].strip()
    s = re.sub(r"^[-*•]\s*", "", s)
    s = _clean_bullet_body(s)
    if not s or not re.match(r"^\S", s) or _is_junk_bullet_body(s):
        return _fallback_one_line(row)
    if len(s) > 500:
        s = s[:497].rstrip() + "..."
    return s


def _summarize_one_article(context: str, row: dict[str, Any]) -> str:
    """One Ollama call → one sentence for this row only."""
    user = f"Section/topic: {context}\n\n{_format_excerpt_block(row)}"
    try:
        raw = ollama_chat(
            [
                {"role": "system", "content": _SYSTEM_SINGLE_ARTICLE},
                {"role": "user", "content": user},
            ]
        )
    except Exception:  # noqa: BLE001 — model/network; fall back to title
        raw = ""
    return _squeeze_single_sentence(raw, row)


def _bullets_one_call_per_article(context: str, rows: list[dict[str, Any]], n: int) -> str:
    lines = [f"- {_summarize_one_article(context, row)}" for row in rows[:n]]
    return "\n".join(lines).strip()


def _normalize_digest_bullets(text: str, *, max_bullets: int) -> str:
    """
    Normalize markers, drop junk/meta lines, enforce max bullet count.
    """
    raw = (text or "").strip()
    if not raw:
        return raw
    lines = raw.splitlines()
    norm: list[str] = []
    for line in lines:
        m = re.match(r"^(\s*)([*+•])\s+(.*)$", line)
        if m:
            norm.append(f"{m.group(1)}- {m.group(3)}".rstrip())
        else:
            norm.append(line.rstrip())

    bullets: list[str] = []
    for line in norm:
        stripped = line.strip()
        m = re.match(r"^-\s+(.*)$", stripped)
        if not m:
            continue
        body = _clean_bullet_body(m.group(1))
        if not body or not re.match(r"^\S", body):
            continue
        if _is_junk_bullet_body(body):
            continue
        bullets.append(f"- {body}")

    if bullets:
        return "\n".join(bullets[:max_bullets]).strip()

    i = 0
    while i < len(norm) and not re.match(r"^-\s+\S", norm[i].strip()):
        i += 1
    if i >= len(norm):
        return raw
    return "\n".join(norm[i : i + max_bullets]).strip()


def _finance_symbol_news_titles(rows: list[dict[str, Any]]) -> list[str]:
    """Distinct Yahoo portfolio news titles (separate from quote snapshot row)."""
    seen: set[str] = set()
    out: list[str] = []
    for row in rows:
        if (row.get("feed_url") or "").strip() != _FINANCE_NEWS_FEED:
            continue
        t = (row.get("title") or "").strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _metrics_lines(rows: list[dict[str, Any]]) -> str:
    """Pull quote fields from portfolio rows (snapshot lines are in content too)."""
    pct = last = prev = cur = None
    for row in rows:
        if row.get("pct_change_day") is not None:
            pct = row.get("pct_change_day")
        if row.get("last_price") is not None:
            last = row.get("last_price")
        if row.get("previous_close") is not None:
            prev = row.get("previous_close")
        if row.get("currency"):
            cur = row.get("currency")
    parts = []
    if pct is not None:
        try:
            p = round(float(pct), 2)
        except (TypeError, ValueError):
            p = pct
        parts.append(f"Day change vs prior close (from data): {p}%")
    if last is not None:
        try:
            lp = round(float(last), 2)
        except (TypeError, ValueError):
            lp = last
        parts.append(f"Last price (from data): {lp} {cur or ''}".strip())
    if prev is not None:
        try:
            pv = round(float(prev), 2)
        except (TypeError, ValueError):
            pv = prev
        parts.append(f"Previous close (from data): {pv} {cur or ''}".strip())
    return "\n".join(parts) if parts else "(No numeric quote fields in this batch.)"


def _numbered_excerpt_chunks(rows: list[dict[str, Any]], n: int) -> str:
    chunks: list[str] = []
    for i, row in enumerate(rows[:n], start=1):
        chunks.append(f"### Article {i}\n{_format_excerpt_block(row)}")
    return "\n\n".join(chunks)


def _user_prompt_finance_symbol(
    symbol: str,
    rows: list[dict[str, Any]],
    *,
    has_news: bool,
) -> str:
    metrics = _metrics_lines(rows)
    news_titles = _finance_symbol_news_titles(rows)
    if news_titles:
        title_block = (
            "Stock-related headlines in this batch (compress into line 2 of your output):\n"
            + "\n".join(f"- {t}" for t in news_titles)
        )
    else:
        title_block = "No stock-specific news headlines are in this batch (quote snapshot only)."

    n = _article_count(rows)
    joined = _numbered_excerpt_chunks(rows, n)

    if has_news:
        return (
            f"Ticker: {symbol}\n\n"
            f"{title_block}\n\n"
            "Output EXACTLY 2 lines only.\n"
            "Line 1: One sentence on trading performance only (numeric summary; round prices to two decimals).\n"
            "Line 2: One sentence that summarizes stock-relevant news from the excerpts — if there are several "
            "headlines, compress them into this single sentence; do not write one line per headline.\n\n"
            f"Numeric summary from ingest:\n{metrics}\n\n"
            f"Excerpts:\n\n{joined}"
        )

    return (
        f"Ticker: {symbol}\n\n"
        f"{title_block}\n\n"
        "Output EXACTLY 2 lines only.\n"
        "Line 1: One sentence on trading performance from the numeric summary (round to two decimals).\n"
        "Line 2: One sentence stating no stock-specific headlines were ingested (quote-only). "
        "Do not repeat numbers from line 1.\n\n"
        f"Numeric summary from ingest:\n{metrics}\n\n"
        f"Excerpts:\n\n{joined}"
    )


def run_digest_for_rows(
    rows: list[dict[str, Any]],
    *,
    run_at: datetime | None = None,
    conn: Any = None,
    print_digest: bool = False,
) -> int:
    """
    Store bullet digests in Postgres.

    For every scope except ``FINANCE:<ticker>``, runs **one Ollama call per article** so the digest
    always has exactly one bullet per ingested row in that group (reliable 1:1 mapping).

    For each portfolio ticker, one batch call produces exactly two bullets (trading + combined news).

    Each digest row is linked to source articles via ``digest_summary_sources`` (``article_guid``).

    Args:
        rows: Same list passed to / produced by ``fetch_news`` for this run.
        run_at: UTC timestamp labeling this digest run; default ``now()``.
        conn: Optional ``psycopg.Connection``; if ``None``, a new connection is used for inserts.
        print_digest: If True, print each ``scope`` and its bullets to stdout before DB insert.

    Returns:
        Number of digest rows inserted.
    """
    if not rows:
        return 0

    rt = run_at or datetime.now(timezone.utc)
    groups = _group_rows(rows)
    out_rows: list[dict[str, Any]] = []

    for (topic, symbol), g_rows in sorted(groups.items(), key=lambda x: (x[0][0], x[0][1] or "")):
        if not g_rows:
            continue
        scope = _scope_key(topic, symbol)
        n_art = _article_count(g_rows)

        if topic == FINANCE_TOPIC and symbol is not None:
            news_titles = _finance_symbol_news_titles(g_rows)
            has_news = len(news_titles) > 0
            user = _user_prompt_finance_symbol(symbol, g_rows, has_news=has_news)
            bullets = _normalize_digest_bullets(
                ollama_chat(
                    [
                        {"role": "system", "content": _SYSTEM_FINANCE_SYMBOL},
                        {"role": "user", "content": user},
                    ]
                ),
                max_bullets=_MAX_BULLETS_FINANCE_SYMBOL,
            )
        elif topic != FINANCE_TOPIC:
            bullets = _bullets_one_call_per_article(topic, g_rows, n_art)
        else:
            bullets = _bullets_one_call_per_article("FINANCE (broad market)", g_rows, n_art)

        out_rows.append(
            {
                "run_at": rt,
                "scope": scope,
                "topic": topic,
                "symbol": symbol,
                "bullets": bullets,
                "source_guids": _source_guids(g_rows),
            }
        )

    if print_digest and out_rows:
        print("\n========== DIGEST SUMMARIES ==========\n")
        for item in out_rows:
            print(f"## {item['scope']}\n")
            print(item["bullets"])
            print()
        print("========================================\n")

    return insert_digest_rows(out_rows, conn=conn)
