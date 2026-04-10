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


def digest_recipient_chat_ids() -> list[str]:
    """
    Chats that receive the digest PDF: ``TELEGRAM_CHAT_ID`` first (if set), then each id in
    comma-separated ``TELEGRAM_DIGEST_CHAT_IDS``, deduplicated.
    """
    seen: set[str] = set()
    out: list[str] = []
    one = _strip_env("TELEGRAM_CHAT_ID")
    if one:
        seen.add(one)
        out.append(one)
    multi = _strip_env("TELEGRAM_DIGEST_CHAT_IDS")
    if multi:
        for part in multi.split(","):
            x = part.strip()
            if x and x not in seen:
                seen.add(x)
                out.append(x)
    return out


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
            "TELEGRAM_CHAT_ID and/or comma-separated TELEGRAM_DIGEST_CHAT_IDS."
        )
    return cfg


def allowed_chat_ids() -> set[str]:
    """
    Chats that may use the RAG bot. Uses TELEGRAM_ALLOWED_CHAT_IDS (comma-separated) when set;
    otherwise TELEGRAM_CHAT_ID only.
    """
    raw = _strip_env("TELEGRAM_ALLOWED_CHAT_IDS")
    if raw:
        return {x.strip() for x in raw.split(",") if x.strip()}
    chat = _strip_env("TELEGRAM_CHAT_ID")
    return {chat} if chat else set()


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
