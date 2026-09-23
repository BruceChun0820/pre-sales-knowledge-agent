from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from app.domain.models import DocumentRecord, ParsedBlock


class Parser(Protocol):
    """Format adapter that returns ordered domain blocks."""

    @property
    def name(self) -> str:
        """Return a stable parser name."""

    @property
    def version(self) -> str:
        """Return the parser version recorded in the manifest."""

    def parse(self, path: Path, *, document: DocumentRecord) -> Iterable[ParsedBlock]:
        """Parse one file without leaking format-library objects."""


class ParserRegistry:
    """Resolve a parser from an explicit file extension allowlist."""

    def __init__(self, parsers: Iterable[tuple[Parser, Iterable[str]]]) -> None:
        self._parsers: dict[str, Parser] = {}
        for parser, extensions in parsers:
            for extension in extensions:
                normalized = extension.lower()
                if not normalized.startswith("."):
                    raise ValueError("parser extensions must start with '.'")
                if normalized in self._parsers:
                    raise ValueError(f"duplicate parser extension: {normalized}")
                self._parsers[normalized] = parser

    def for_path(self, path: Path) -> Parser:
        try:
            return self._parsers[path.suffix.lower()]
        except KeyError as exc:
            raise ValueError(
                f"no parser registered for extension: {path.suffix or '<none>'}"
            ) from exc
