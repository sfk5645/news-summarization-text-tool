"""CLI: ``python -m app.rag ask \"Your question\"``."""

from __future__ import annotations

import argparse
import json
import sys


def main() -> None:
    p = argparse.ArgumentParser(description="RAG over latest news batch (pgvector + Ollama)")
    sub = p.add_subparsers(dest="cmd", required=True)

    ask_p = sub.add_parser("ask", help="Ask a question against the latest indexed batch")
    ask_p.add_argument(
        "-k",
        type=int,
        default=8,
        help="Number of chunks to retrieve (default 8)",
    )
    ask_p.add_argument(
        "--json",
        action="store_true",
        help="Print JSON {answer, sources}",
    )
    ask_p.add_argument("question", nargs="+", help="Question (words after options)")

    args = p.parse_args()
    if args.cmd == "ask":
        q = " ".join(args.question).strip()
        if not q:
            print("Usage: python -m app.rag ask Your question here", file=sys.stderr)
            sys.exit(1)
        from app.rag.query import ask_latest_news

        result = ask_latest_news(q, k=args.k)
        if args.json:
            print(json.dumps({"answer": result.answer, "sources": result.sources}, indent=2))
        else:
            print(result.answer)
            if result.sources:
                print("\nSources:")
                for s in result.sources:
                    print(f"- {s.get('title', '')} ({s.get('topic', '')})")
                    if s.get("url"):
                        print(f"  {s['url']}")


if __name__ == "__main__":
    main()
