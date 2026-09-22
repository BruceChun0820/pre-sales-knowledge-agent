from __future__ import annotations

from .base import ParserRegistry
from .docx import DocxParser
from .pdf import PdfParser
from .text import MarkdownParser, TextParser


def default_parser_registry() -> ParserRegistry:
    """Build the Phase 1 registry for the four approved source formats."""

    return ParserRegistry(
        (
            (PdfParser(), (".pdf",)),
            (DocxParser(), (".docx",)),
            (MarkdownParser(), (".md",)),
            (TextParser(), (".txt",)),
        )
    )
