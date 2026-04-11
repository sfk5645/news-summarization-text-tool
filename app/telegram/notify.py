"""Send the digest PDF to Telegram after a successful ingest + summarize run."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.telegram.api import send_document
from app.telegram.config import require_digest_config
from app.telegram.pdf_digest import build_digest_pdf_bytes


def send_digest_pdf(digest_rows: list[dict[str, Any]]) -> None:
    if not digest_rows:
        return
    cfg = require_digest_config()
    pdf_bytes = build_digest_pdf_bytes(digest_rows)
    run_at = digest_rows[0]["run_at"]
    if isinstance(run_at, datetime):
        stamp = run_at.strftime("%Y-%m-%d")
    else:
        stamp = "digest"
    filename = f"news-digest-{stamp}.pdf"
    caption = f"Daily news digest ({stamp})"
    errors: list[str] = []
    for chat_id in cfg.digest_chat_ids:
        cid = (chat_id or "").strip()
        if not cid:
            continue
        try:
            send_document(cfg.bot_token, cid, filename, pdf_bytes, caption=caption)
        except Exception as ex:  # noqa: BLE001 — log per-chat; one bad chat must not block others
            errors.append(f"chat_id={cid!r}: {ex}")
    if errors:
        raise RuntimeError(
            "Telegram digest PDF failed for one or more chats:\n" + "\n".join(errors)
        )
