"""Call a local Ollama chat model over HTTP."""

from __future__ import annotations

import os
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()


def ollama_chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    base_url: str | None = None,
    timeout_s: float = 300.0,
) -> str:
    """
    Send chat messages to Ollama and return the assistant text.

    Args:
        messages: Ollama-format list of ``{"role": "system"|"user"|"assistant", "content": "..."}``.
        model: Overrides ``OLLAMA_MODEL`` env (required if env unset).
        base_url: Overrides ``OLLAMA_BASE_URL`` (default ``http://127.0.0.1:11434``).
        timeout_s: Request timeout in seconds.

    Returns:
        Assistant message content string.

    Raises:
        RuntimeError: If model cannot be resolved or the API returns an error.
    """
    url = (base_url or os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").rstrip(
        "/"
    )
    m = (model or os.getenv("OLLAMA_MODEL") or "").strip()
    if not m:
        raise RuntimeError(
            "Set OLLAMA_MODEL in .env (e.g. llama3) or pass model= to ollama_chat."
        )
    payload: dict[str, Any] = {
        "model": m,
        "messages": messages,
        "stream": False,
    }
    with httpx.Client(timeout=timeout_s) as client:
        r = client.post(f"{url}/api/chat", json=payload)
        r.raise_for_status()
        data = r.json()
    msg = data.get("message") or {}
    content = msg.get("content")
    if not content or not isinstance(content, str):
        raise RuntimeError(f"Unexpected Ollama response: {data!r}")
    return content.strip()
