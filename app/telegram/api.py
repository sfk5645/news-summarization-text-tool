"""Minimal Telegram Bot HTTP API (``httpx``), no extra SDK."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import httpx


def _base(token: str) -> str:
    return f"https://api.telegram.org/bot{token}"


def send_message(token: str, chat_id: str, text: str, *, parse_mode: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    r = httpx.post(f"{_base(token)}/sendMessage", json=payload, timeout=60.0)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram sendMessage failed: {data!r}")
    return data


def send_document(
    token: str,
    chat_id: str,
    filename: str,
    data: bytes,
    *,
    caption: str | None = None,
) -> dict[str, Any]:
    files = {"document": (filename, BytesIO(data), "application/pdf")}
    form: dict[str, Any] = {"chat_id": chat_id}
    if caption:
        form["caption"] = caption[:1024]
    r = httpx.post(f"{_base(token)}/sendDocument", data=form, files=files, timeout=120.0)
    r.raise_for_status()
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"Telegram sendDocument failed: {body!r}")
    return body


def get_updates(token: str, *, offset: int | None = None, timeout: int = 25) -> dict[str, Any]:
    params: dict[str, Any] = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    r = httpx.get(f"{_base(token)}/getUpdates", params=params, timeout=float(timeout + 5))
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram getUpdates failed: {data!r}")
    return data
