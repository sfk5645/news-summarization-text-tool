"""Build a single PDF from digest rows (topic emoji headings; finance symbols as subsections)."""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from fpdf import FPDF

from app.news.news import FINANCE_TOPIC, RSS_FEEDS_BY_TOPIC

_FONT_DIR = Path(__file__).resolve().parent / "fonts"

# Topic markers drawn with SymbolEmoji (Noto Sans Symbols2), except these BMP glyphs which
# that font lacks: strip U+FE0F from emoji strings before drawing.
_TOPIC_EMOJI: dict[str, str] = {
    "WORLD": "🌍",
    "NATIONAL": "🗞️",
    "LOCAL": "\u25aa",  # ▪ replaces 📍 (U+1F4CD); U+2316 missing in bundled DejaVu
    "POLITICS": "🏛️",
    "BUSINESS": "\u25c6",  # ◆ replaces 💼 (U+1F4BC)
    "FINANCE": "📈",
    "TECHNOLOGY": "💻",
    "SCIENCE": "\u2697",  # ⚗ replaces 🔬 (U+1F52C)
    "HEALTH": "\u2695",  # ⚕ replaces 🏥 (U+1F3E5)
    "SPORTS": "⚽",
    "ENTERTAINMENT": "🎬",
    "UNKNOWN": "📋",
}

# Draw with DejaVu (outline) — Noto Symbols2 omits these; DejaVu Sans regular includes them.
_BMP_MARKER_FOR_DEJAVU: frozenset[str] = frozenset(
    {
        "\u25aa",  # ▪ LOCAL
        "\u25c6",  # ◆ BUSINESS
        "\u2697",  # ⚗ SCIENCE
        "\u2695",  # ⚕ HEALTH
    }
)


def _register_fonts(pdf: FPDF) -> None:
    regular = _FONT_DIR / "DejaVuSans.ttf"
    bold = _FONT_DIR / "DejaVuSans-Bold.ttf"
    symbols2 = _FONT_DIR / "NotoSansSymbols2-Regular.ttf"
    if not regular.is_file() or not bold.is_file():
        raise RuntimeError(
            "PDF fonts missing: add DejaVuSans.ttf and DejaVuSans-Bold.ttf under "
            f"{_FONT_DIR} (see DejaVu Fonts license)."
        )
    if not symbols2.is_file():
        raise RuntimeError(
            f"PDF emoji font missing: NotoSansSymbols2-Regular.ttf under {_FONT_DIR} "
            "(SIL Open Font License)."
        )
    pdf.add_font("DejaVu", "", str(regular))
    pdf.add_font("DejaVu", "B", str(bold))
    pdf.add_font("SymbolEmoji", "", str(symbols2))


def _topic_display_order() -> list[str]:
    order: list[str] = []
    for k in RSS_FEEDS_BY_TOPIC:
        if k != FINANCE_TOPIC and k not in order:
            order.append(k)
    order.append("UNKNOWN")
    return order


def _organize(
    rows: list[dict[str, Any]],
) -> tuple[datetime, list[tuple[str, str]], str | None, list[tuple[str, str]]]:
    if not rows:
        raise ValueError("digest rows required for PDF")
    run_at = rows[0]["run_at"]
    if not isinstance(run_at, datetime):
        raise TypeError("run_at must be a datetime")

    non_fin: dict[str, str] = {}
    finance_market: str | None = None
    finance_symbols: list[tuple[str, str]] = []

    for row in rows:
        topic = (row.get("topic") or "UNKNOWN").strip() or "UNKNOWN"
        sym = row.get("symbol")
        bullets = (row.get("bullets") or "").strip()
        if not bullets:
            continue
        if topic != FINANCE_TOPIC:
            non_fin[topic] = bullets
        elif sym is None or not str(sym).strip():
            finance_market = bullets
        else:
            finance_symbols.append((str(sym).strip().upper(), bullets))

    ordered_non_fin: list[tuple[str, str]] = []
    seen: set[str] = set()
    for t in _topic_display_order():
        if t in non_fin:
            ordered_non_fin.append((t, non_fin[t]))
            seen.add(t)
    for t in sorted(non_fin.keys()):
        if t not in seen:
            ordered_non_fin.append((t, non_fin[t]))

    finance_symbols.sort(key=lambda x: x[0])
    return run_at, ordered_non_fin, finance_market, finance_symbols


class _DigestPDF(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=14)
        self.set_margins(16, 16, 16)

    def section_title(self, emoji: str, title_text: str) -> None:
        s = emoji.replace("\ufe0f", "")
        if s in _BMP_MARKER_FOR_DEJAVU:
            self.set_font("DejaVu", "", 14)
            self.write(8, s)
        else:
            self.set_font("SymbolEmoji", "", 14)
            self.write(8, s)
        self.set_font("DejaVu", "B", 13)
        self.write(8, f"  {title_text}")
        self.ln(9)

    def subsection_title(self, title_text: str) -> None:
        """Finance subsections use DejaVu only (emoji fonts omit some newspaper / chart glyphs)."""
        self.set_font("DejaVu", "B", 11)
        inner = self.w - self.l_margin - self.r_margin - 4
        self.set_x(self.l_margin + 4)
        self.multi_cell(inner, 6, title_text, new_x="LMARGIN", new_y="NEXT")
        self.ln(0.5)

    def body_block(self, text: str, *, indent_mm: float = 0) -> None:
        self.set_font("DejaVu", "", 10)
        w = self.w - self.l_margin - self.r_margin - indent_mm
        self.set_x(self.l_margin + indent_mm)
        self.multi_cell(w, 5, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)


def build_digest_pdf_bytes(rows: list[dict[str, Any]], *, greeting: str | None = None) -> bytes:
    run_at, non_fin, finance_market, finance_symbols = _organize(rows)
    if run_at.tzinfo is not None:
        title_time = run_at.strftime("%Y-%m-%d %H:%M UTC")
    else:
        title_time = run_at.strftime("%Y-%m-%d %H:%M")

    pdf = _DigestPDF()
    _register_fonts(pdf)
    pdf.add_page()
    pdf.set_font("DejaVu", "B", 16)
    pdf.multi_cell(0, 8, "Your Daily News Digest", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 11)
    pdf.multi_cell(0, 6, title_time, new_x="LMARGIN", new_y="NEXT")
    if greeting:
        pdf.multi_cell(0, 6, greeting.strip(), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    for topic, bullets in non_fin:
        emoji = _TOPIC_EMOJI.get(topic, "📌")
        pdf.section_title(emoji, topic.replace("_", " "))
        pdf.body_block(bullets)

    if finance_market or finance_symbols:
        pdf.section_title(_TOPIC_EMOJI.get(FINANCE_TOPIC, "📈"), "Finance")
        if finance_market:
            pdf.subsection_title("Broad market & finance feed")
            pdf.body_block(finance_market, indent_mm=4)
        for sym, bullets in finance_symbols:
            pdf.subsection_title(f"Symbol: {sym}")
            pdf.body_block(bullets, indent_mm=4)

    buf = BytesIO()
    pdf.output(buf)
    return buf.getvalue()
