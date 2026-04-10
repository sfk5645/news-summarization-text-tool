"""Long-polling Telegram bot: RAG answers over the latest indexed news batch."""

from __future__ import annotations

import sys
import time

from app.rag.query import ask_latest_news
from app.telegram.api import get_updates, send_message
from app.telegram.config import require_bot_access_config


def _chunks(text: str, limit: int = 4096) -> list[str]:
    text = (text or "").strip()
    if not text:
        return ["(empty reply)"]
    if len(text) <= limit:
        return [text]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


def _format_answer(answer: str, sources: list[dict[str, str]]) -> str:
    lines = [answer]
    if sources:
        lines.append("")
        lines.append("Sources:")
        for s in sources[:8]:
            title = (s.get("title") or "").strip()
            topic = (s.get("topic") or "").strip()
            url = (s.get("url") or "").strip()
            lines.append(f"• {title} ({topic})")
            if url:
                lines.append(f"  {url}")
    return "\n".join(lines)


def run_polling() -> None:
    token, allowed = require_bot_access_config()
    print(
        "Telegram RAG bot polling (Ctrl+C to stop). Answering chats:",
        ", ".join(sorted(allowed)),
        file=sys.stderr,
    )
    offset: int | None = None
    while True:
        try:
            data = get_updates(token, offset=offset, timeout=25)
        except Exception as ex:  # noqa: BLE001 — keep polling on network errors
            print(f"getUpdates error: {ex}; retrying in 5s", file=sys.stderr)
            time.sleep(5)
            continue
        for upd in data.get("result") or []:
            offset = upd["update_id"] + 1
            msg = upd.get("message") or upd.get("edited_message")
            if not msg:
                continue
            chat = msg.get("chat") or {}
            cid = str(chat.get("id") or "")
            if cid not in allowed:
                continue
            text = (msg.get("text") or "").strip()
            if not text:
                continue
            low = text.lower()
            if low in ("/start", "/help"):
                send_message(
                    token,
                    cid,
                    "Send a question about your latest ingested news batch. "
                    "Replies use RAG over that batch only. "
                    "Run ingest (with summarize and RAG indexing) before asking.",
                )
                continue
            try:
                result = ask_latest_news(text)
                body = _format_answer(result.answer, result.sources)
            except Exception as ex:  # noqa: BLE001 — surface model/DB errors to the user
                body = f"Could not answer: {ex}"
            for part in _chunks(body):
                send_message(token, cid, part)
