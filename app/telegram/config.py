"""Environment-driven Telegram settings (``python-dotenv`` loads ``.env`` from the app)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str
    digest_chat_ids: tuple[str, ...]


def _strip_env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def allowed_chat_id_list() -> list[str]:
    """
    Chats allowed for the RAG bot and (same order) recipients for the digest PDF.

    If ``TELEGRAM_ALLOWED_CHAT_IDS`` is set: that comma-separated list (deduped, order kept),
    with ``TELEGRAM_CHAT_ID`` inserted at the front when set and not already in the list.
    Otherwise: ``[TELEGRAM_CHAT_ID]`` when that is set, else empty.
    """
    raw = _strip_env("TELEGRAM_ALLOWED_CHAT_IDS")
    one = _strip_env("TELEGRAM_CHAT_ID")
    if raw:
        seen: set[str] = set()
        out: list[str] = []
        if one:
            seen.add(one)
            out.append(one)
        for part in raw.split(","):
            x = part.strip()
            if x and x not in seen:
                seen.add(x)
                out.append(x)
        return out
    return [one] if one else []


def digest_recipient_chat_ids() -> list[str]:
    """Same membership and order as :func:`allowed_chat_id_list`."""
    return allowed_chat_id_list()


def load_telegram_config() -> TelegramConfig | None:
    token = _strip_env("TELEGRAM_BOT_TOKEN")
    if not token:
        return None
    chats = digest_recipient_chat_ids()
    if not chats:
        return None
    return TelegramConfig(bot_token=token, digest_chat_ids=tuple(chats))


def require_digest_config() -> TelegramConfig:
    cfg = load_telegram_config()
    if not cfg:
        raise RuntimeError(
            "Telegram digest needs TELEGRAM_BOT_TOKEN and at least one recipient: "
            "TELEGRAM_ALLOWED_CHAT_IDS and/or TELEGRAM_CHAT_ID."
        )
    return cfg


def allowed_chat_ids() -> set[str]:
    """Set of chats that may use the RAG bot (same ids as digest PDF list)."""
    return set(allowed_chat_id_list())


def require_bot_token() -> str:
    token = _strip_env("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN to run the Telegram bot.")
    return token


def require_bot_access_config() -> tuple[str, set[str]]:
    token = require_bot_token()
    chats = allowed_chat_ids()
    if not chats:
        raise RuntimeError(
            "Set TELEGRAM_CHAT_ID or TELEGRAM_ALLOWED_CHAT_IDS so the bot knows which chats to answer."
        )
    return token, chats
