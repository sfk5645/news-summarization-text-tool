"""RSS ingestion: fetch recent articles per topic and extract plain text for storage / RAG."""

import re
import time
from datetime import date, datetime, timezone
from typing import Any

import feedparser
import trafilatura
import yfinance as yf

# Topic label -> RSS URL. ``None`` means the topic is skipped (no feed configured).
RSS_FEEDS_BY_TOPIC: dict[str, str | None] = {
    "WORLD": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "NATIONAL": "https://rss.nytimes.com/services/xml/rss/nyt/US.xml",
    "LOCAL": "https://wtop.com/local/virginia/feed/",
    "POLITICS": "https://feeds.bbci.co.uk/news/politics/rss.xml",
    "BUSINESS": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "FINANCE": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "TECHNOLOGY": "https://techcrunch.com/feed/",
    "SCIENCE": "https://www.sciencedaily.com/rss/top/science.xml",
    "HEALTH": "https://www.sciencedaily.com/rss/top/health.xml",
    "SPORTS": "https://www.espn.com/espn/rss/news",
    "ENTERTAINMENT": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
}

FINANCE_TOPIC = "FINANCE"


def _empty_portfolio_fields() -> dict[str, Any]:
    return {
        "symbol": None,
        "pct_change_day": None,
        "last_price": None,
        "previous_close": None,
        "currency": None,
    }


def _published_iso(entry: Any) -> str | None:
    """
    Build a normalized publish time from a feedparser entry.

    Args:
        entry: A single RSS/Atom entry object from feedparser (e.g. ``feed.entries[i]``).

    Returns:
        UTC ISO 8601 string from ``published_parsed`` when parseable; otherwise the raw
        ``published`` string if present; otherwise ``None``.
    """
    parsed = getattr(entry, "published_parsed", None)
    if parsed:
        try:
            dt = datetime.fromtimestamp(time.mktime(parsed), tz=timezone.utc)
            return dt.isoformat()
        except (TypeError, ValueError, OverflowError):
            pass
    published = getattr(entry, "published", None)
    return str(published) if published else None


def _rss_snippet_plain(html_or_text: str) -> str:
    """
    Turn RSS HTML (or plain text) into a single-line plain string.

    Args:
        html_or_text: ``summary`` / ``description`` from the feed, often HTML.

    Returns:
        Whitespace-normalized plain text with tags removed; empty string if input is empty.
    """
    if not html_or_text:
        return ""
    plain = re.sub(r"<[^>]+>", " ", html_or_text)
    return re.sub(r"\s+", " ", plain).strip()


def _article_content(url: str, rss_description: str) -> str:
    """
    Resolve full article plain text for RAG (page fetch first, then RSS fallbacks).

    Args:
        url: Canonical article link from the feed item.
        rss_description: HTML or text from the entry's ``summary`` / ``description``.

    Returns:
        Stripped plain body from trafilatura when the page or RSS HTML yields content;
        otherwise tag-stripped text from ``rss_description``.
    """
    if url:
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            extracted = trafilatura.extract(downloaded)
            if extracted and extracted.strip():
                return extracted.strip()
    if rss_description:
        extracted = trafilatura.extract(rss_description)
        if extracted and extracted.strip():
            return extracted.strip()
    return _rss_snippet_plain(rss_description)


def _quote_metrics(symbol: str) -> dict[str, Any]:
    """
    Latest price and approximate day percent change via yfinance.

    Args:
        symbol: Equity/ETF ticker (e.g. ``AAPL``).

    Returns:
        Dict with ``symbol``, optional ``last_price``, ``previous_close``, ``pct_change_day``
        (percent points, e.g. ``1.25`` for +1.25%), ``currency``, and ``error`` if lookup failed.
    """
    sym = symbol.strip().upper()
    out: dict[str, Any] = {
        "symbol": sym,
        "last_price": None,
        "previous_close": None,
        "pct_change_day": None,
        "currency": None,
        "error": None,
    }
    try:
        t = yf.Ticker(sym)
        fi = getattr(t, "fast_info", None)
        if fi is not None:
            last = fi.get("last_price")
            prev = fi.get("previous_close")
            if last is not None and prev:
                out["last_price"] = float(last)
                out["previous_close"] = float(prev)
                out["pct_change_day"] = round(
                    (float(last) - float(prev)) / float(prev) * 100.0, 4
                )
            out["currency"] = fi.get("currency")
        if out["pct_change_day"] is None:
            hist = t.history(period="5d")
            if hist is not None and len(hist) >= 2:
                closes = hist["Close"].dropna()
                if len(closes) >= 2:
                    last_f = float(closes.iloc[-1])
                    prev_f = float(closes.iloc[-2])
                    out["last_price"] = last_f
                    out["previous_close"] = prev_f
                    out["pct_change_day"] = round(
                        (last_f - prev_f) / prev_f * 100.0, 4
                    )
    except Exception as exc: 
        out["error"] = str(exc)
    return out


def _published_iso_from_unix(ts: Any) -> str | None:
    if ts is None:
        return None
    try:
        dt = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        return dt.isoformat()
    except (TypeError, ValueError, OSError):
        return None


def _finance_portfolio_rows(
    limit_news_per_symbol: int,
    fetch_article_body: bool,
) -> list[dict[str, Any]]:
    """
    Rows for ``FINANCE_TOPIC`` only: E*TRADE portfolio symbols (see ``e_trade_service``)
    with Yahoo quote snapshot and headline news per symbol.
    """
    from app.users.e_trade_service import get_portfolio_ticket_symbols

    raw = get_portfolio_ticket_symbols()
    seen: set[str] = set()
    symbols: list[str] = []
    for s in raw:
        u = (s or "").strip().upper()
        if u and u not in seen:
            seen.add(u)
            symbols.append(u)

    rows: list[dict[str, Any]] = []
    today = date.today().isoformat()

    for symbol in symbols:
        metrics = _quote_metrics(symbol)
        pct = metrics.get("pct_change_day")
        last_p = metrics.get("last_price")
        prev_p = metrics.get("previous_close")
        cur = metrics.get("currency") or ""
        err = metrics.get("error")

        snap_lines = [
            f"Ticker: {symbol}",
            f"Day change (approx. vs prior close): {pct}%"
            if pct is not None
            else "Day change: unavailable",
        ]
        if last_p is not None:
            snap_lines.append(f"Last price: {last_p} {cur}".strip())
        if prev_p is not None:
            snap_lines.append(f"Previous close: {prev_p} {cur}".strip())
        if err:
            snap_lines.append(f"Quote note: {err}")
        snapshot_content = "\n".join(snap_lines)

        rows.append(
            {
                "topic": FINANCE_TOPIC,
                "title": f"{symbol} — portfolio performance snapshot",
                "url": f"https://finance.yahoo.com/quote/{symbol}",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "content": snapshot_content,
                "guid": f"finance:portfolio:snapshot:{symbol}:{today}",
                "feed_url": "finance:portfolio:quote",
                "symbol": symbol,
                "pct_change_day": pct,
                "last_price": last_p,
                "previous_close": prev_p,
                "currency": metrics.get("currency"),
            }
        )

        try:
            t = yf.Ticker(symbol)
            news_items = list(getattr(t, "news", None) or [])
        except Exception:  # noqa: BLE001
            news_items = []

        for item in news_items[:limit_news_per_symbol]:
            title = (item.get("title") or "").strip()
            link = (item.get("link") or "").strip()
            publisher = (item.get("publisher") or "").strip()
            pub_ts = item.get("providerPublishTime")
            published_at = _published_iso_from_unix(pub_ts)
            if not title and not link:
                continue

            if fetch_article_body and link:
                body = _article_content(link, "")
            else:
                body = " ".join(
                    x for x in (title, f"Source: {publisher}" if publisher else "") if x
                ).strip()

            guid_key = item.get("uuid") or link or title
            rows.append(
                {
                    "topic": FINANCE_TOPIC,
                    "title": title or f"News related to {symbol}",
                    "url": link or f"https://finance.yahoo.com/quote/{symbol}",
                    "published_at": published_at,
                    "content": body or title,
                    "guid": f"finance:portfolio:news:{symbol}:{guid_key}",
                    "feed_url": "finance:portfolio:news",
                    "symbol": symbol,
                    "pct_change_day": pct,
                    "last_price": last_p,
                    "previous_close": prev_p,
                    "currency": metrics.get("currency"),
                }
            )

    return rows


def fetch_news(
    limit_per_topic: int = 5,
    *,
    include_finance_portfolio: bool = True,
    limit_finance_portfolio_news_per_symbol: int = 5,
    finance_portfolio_fetch_full_text: bool = True,
) -> list[dict[str, Any]]:
    """
    Load recent articles from RSS (full text via trafilatura) and optional finance extras.

    For topic ``FINANCE`` only, after the Dow Jones RSS items, appends rows for each symbol
    from ``get_portfolio_ticket_symbols()``: a quote snapshot (``%`` up/down vs prior close)
    and Yahoo Finance news lines. All other topics behave as plain RSS.

    Args:
        limit_per_topic: Maximum RSS items per topic (newest-first typical).
        include_finance_portfolio: If False, ``FINANCE`` is only the market RSS feed.
        limit_finance_portfolio_news_per_symbol: Max Yahoo headlines per portfolio symbol.
        finance_portfolio_fetch_full_text: If True, trafilatura-fetch each portfolio news URL
            (slow). If False, ``content`` is title + publisher.

    Returns:
        Row dicts all share the same keys. Base fields: ``topic``, ``title``, ``url``,
        ``published_at``, ``content``, ``guid``, ``feed_url``. Portfolio fields
        (``symbol``, ``pct_change_day``, ``last_price``, ``previous_close``, ``currency``)
        are ``None`` except on finance portfolio snapshot/news rows. Dow Jones RSS rows
        under ``FINANCE`` also have those portfolio fields set to ``None``.
    """
    articles: list[dict[str, Any]] = []

    for topic, url in RSS_FEEDS_BY_TOPIC.items():
        if not url:
            continue

        feed = feedparser.parse(url)
        entries = getattr(feed, "entries", []) or []
        for entry in entries[:limit_per_topic]:
            title = (getattr(entry, "title", None) or "").strip()
            link = (getattr(entry, "link", None) or "").strip()
            rss_description = getattr(entry, "summary", None) or getattr(
                entry, "description", None
            ) or ""
            guid = (getattr(entry, "id", None) or link or "").strip()

            row: dict[str, Any] = {
                "topic": topic,
                "title": title,
                "url": link,
                "published_at": _published_iso(entry),
                "content": _article_content(link, rss_description),
                "guid": guid,
                "feed_url": url,
            }
            row.update(_empty_portfolio_fields())
            articles.append(row)

        if topic == FINANCE_TOPIC and include_finance_portfolio:
            articles.extend(
                _finance_portfolio_rows(
                    limit_news_per_symbol=limit_finance_portfolio_news_per_symbol,
                    fetch_article_body=finance_portfolio_fetch_full_text,
                )
            )

    return articles


if __name__ == "__main__":
    for row in fetch_news(
        limit_per_topic=1,
        include_finance_portfolio=True,
        limit_finance_portfolio_news_per_symbol=1,
        finance_portfolio_fetch_full_text=False,
    ):
        print({**row, "content": f"{len(row['content'])} chars"})
