"""Send the digest PDF to Telegram after a successful ingest + summarize run."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.telegram.api import get_chat, send_document
from app.telegram.config import require_digest_config
from app.telegram.digest_greeting import (
    digest_greeting_line,
    digest_telegram_caption,
    telegram_display_name,
)
from app.telegram.pdf_digest import build_digest_pdf_bytes


def send_digest_pdf(digest_rows: list[dict[str, Any]]) -> None:
    if not digest_rows:
        return
    cfg = require_digest_config()
    run_at = digest_rows[0]["run_at"]
    if isinstance(run_at, datetime):
        stamp = run_at.strftime("%Y-%m-%d")
    else:
        stamp = "digest"
    filename = f"news-digest-{stamp}.pdf"
    errors: list[str] = []
    for chat_id in cfg.digest_chat_ids:
        cid = (chat_id or "").strip()
        if not cid:
            continue
        display_name: str | None = None
        try:
            display_name = telegram_display_name(get_chat(cfg.bot_token, cid))
        except Exception:
            pass
        greeting = digest_greeting_line(display_name=display_name)
        pdf_bytes = build_digest_pdf_bytes(digest_rows, greeting=greeting)
        caption = digest_telegram_caption(display_name=display_name, stamp=stamp)
        try:
            send_document(cfg.bot_token, cid, filename, pdf_bytes, caption=caption)
        except Exception as ex:  # noqa: BLE001 — log per-chat; one bad chat must not block others
            errors.append(f"chat_id={cid!r}: {ex}")
    if errors:
        raise RuntimeError(
            "Telegram digest PDF failed for one or more chats:\n" + "\n".join(errors)
        )
