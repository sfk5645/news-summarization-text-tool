"""CLI: create schema and/or fetch news into Postgres."""

from __future__ import annotations

import argparse

from app.db.articles import fetch_and_store_news, init_schema


def main() -> None:
    p = argparse.ArgumentParser(description="Load news into Postgres")
    p.add_argument(
        "--init-schema",
        action="store_true",
        help="Run sql/schema.sql (CREATE TABLE / indexes)",
    )
    p.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Only run --init-schema; do not call fetch_news",
    )
    p.add_argument(
        "--limit-per-topic",
        type=int,
        default=5,
        help="Passed to fetch_news (default 5)",
    )
    p.add_argument(
        "--no-portfolio",
        action="store_true",
        help="fetch_news(..., include_finance_portfolio=False)",
    )
    p.add_argument(
        "--portfolio-news",
        type=int,
        default=5,
        help="limit_finance_portfolio_news_per_symbol (default 5)",
    )
    p.add_argument(
        "--portfolio-no-fulltext",
        action="store_true",
        help="finance_portfolio_fetch_full_text=False (faster)",
    )
    p.add_argument(
        "--no-summarize",
        action="store_true",
        help="Skip Ollama bullet digest after ingest (default: summarize)",
    )
    p.add_argument(
        "--print-digest",
        action="store_true",
        help="Print each topic/symbol digest to stdout after Ollama (requires summarization)",
    )
    args = p.parse_args()

    if args.init_schema:
        init_schema()
        print("Schema applied.")

    if args.skip_fetch:
        return

    summarize = not args.no_summarize
    n = fetch_and_store_news(
        limit_per_topic=args.limit_per_topic,
        include_finance_portfolio=not args.no_portfolio,
        limit_finance_portfolio_news_per_symbol=args.portfolio_news,
        finance_portfolio_fetch_full_text=not args.portfolio_no_fulltext,
        summarize_digest=summarize,
        print_digest=summarize and args.print_digest,
    )
    print(f"Upserted {n} article row(s).")
    if summarize:
        print("Digest summaries written (see digest_summaries table).")


if __name__ == "__main__":
    main()
