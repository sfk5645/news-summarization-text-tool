"""CLI: ``python -m app.telegram poll`` — RAG Q&A via Telegram long polling."""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    p = argparse.ArgumentParser(description="Telegram integration for news digest + RAG")
    sub = p.add_subparsers(dest="cmd", required=True)

    poll_p = sub.add_parser("poll", help="Run bot long polling (answer questions with RAG)")
    poll_p.set_defaults(func=_cmd_poll)

    args = p.parse_args()
    args.func()


def _cmd_poll() -> None:
    from app.telegram.bot import run_polling

    try:
        run_polling()
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)


if __name__ == "__main__":
    main()
