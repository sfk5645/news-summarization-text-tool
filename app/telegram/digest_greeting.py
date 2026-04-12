"""Time-of-day greeting for digest PDF / Telegram caption (uses system local time)."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def telegram_display_name(chat: dict[str, Any]) -> str | None:
    """Best-effort label from ``getChat`` ``result`` (private, group, or channel)."""
    for key in ("first_name", "title"):
        v = (chat.get(key) or "").strip()
        if v:
            return v
    u = (chat.get("username") or "").strip()
    if u:
        return f"@{u}"
    return None


def digest_greeting_line(*, display_name: str | None = None, when: datetime | None = None) -> str:
    """
    Short lead for the PDF, e.g. ``Good morning, Alex.`` or ``Good evening.`` when no name.

    Hours (local clock): morning 05–11, afternoon 12–16, evening 17–21, night 22–04.
    """
    when = when or datetime.now().astimezone()
    h = when.hour
    if 5 <= h < 12:
        stem = "Good morning"
    elif 12 <= h < 17:
        stem = "Good afternoon"
    elif 17 <= h < 22:
        stem = "Good evening"
    else:
        stem = "Good night"

    if display_name:
        return f"{stem}, {display_name}."
    return f"{stem}."


def digest_telegram_caption(*, display_name: str | None, stamp: str, when: datetime | None = None) -> str:
    """
    Full Telegram caption: time-of-day greeting plus what the attached PDF is.

    ``stamp`` is the digest run date (``YYYY-MM-DD``) shown in the closing phrase.
    """
    lead = digest_greeting_line(display_name=display_name, when=when)
    rest = (
        "Attached in this message is a PDF with summaries of the latest news, "
        "grouped by topic with finance highlights where relevant. "
        f"This digest is for {stamp}."
    )
    return f"{lead}\n\n{rest}"
