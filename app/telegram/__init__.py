"""Telegram: PDF digest delivery after ingest and optional RAG Q&A via polling bot."""

from app.telegram.notify import send_digest_pdf

__all__ = ["send_digest_pdf"]
