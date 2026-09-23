from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from app.domain.interfaces import ChunkingStrategy, TextCleaner
from app.domain.models import BlockType, Chunk, DocumentRecord, ParsedBlock, SourceLocation

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[._/-][A-Za-z0-9]+)*|[\u3400-\u9fff]|[^\s]")
_ATOMIC_PATTERN = re.compile(
    r"\s+|[A-Za-z0-9]+(?:[._/-][A-Za-z0-9]+)*|[\u3400-\u9fff]|.",
    re.DOTALL,
)
_SENTENCE_END = frozenset(".!?。！？")


class TokenCounter(Protocol):
    """Count tokens using the tokenizer selected by the embedding adapter."""

    def count(self, text: str) -> int:
        """Return the token count for non-empty text."""


class RegexTokenCounter:
    """Deterministic dependency-free counter for tests and pre-benchmark experiments."""

    def count(self, text: str) -> int:
        return len(_TOKEN_PATTERN.findall(text))


@dataclass(frozen=True)
class ChunkingConfig:
    """Token and section boundaries for one reproducible chunking experiment."""

    target_tokens: int = 512
    max_tokens: int = 512
    overlap_tokens: int = 64
    allow_cross_top_level_sections: bool = False

    def __post_init__(self) -> None:
        if self.target_tokens < 1:
            raise ValueError("target_tokens must be positive")
        if self.max_tokens < self.target_tokens:
            raise ValueError("max_tokens must be greater than or equal to target_tokens")
        if self.overlap_tokens < 0:
            raise ValueError("overlap_tokens must not be negative")
        if self.overlap_tokens >= self.max_tokens:
            raise ValueError("overlap_tokens must be less than max_tokens")


class ChunkingError(ValueError):
    """Raised when parsed blocks cannot be converted into valid chunks."""


class IndivisibleTokenError(ChunkingError):
    """Report source text that one tokenizer treats as larger than the hard limit."""

    def __init__(self, text: str, token_count: int, max_tokens: int) -> None:
        preview = text[:40].replace("\n", " ")
        super().__init__(
            f"indivisible token exceeds max_tokens: {token_count} > {max_tokens}; text={preview!r}"
        )
        self.text = text
        self.token_count = token_count
        self.max_tokens = max_tokens


@dataclass(frozen=True)
class _ChunkDraft:
    text: str
    blocks: tuple[ParsedBlock, ...]


def _section_path(block: ParsedBlock) -> tuple[str, ...]:
    return block.section_path or block.source_location.section_path


def _common_section_path(blocks: Sequence[ParsedBlock]) -> tuple[str, ...]:
    paths = [_section_path(block) for block in blocks]
    if not paths:
        return ()
    prefix: list[str] = []
    for values in zip(*paths, strict=False):
        if len(set(values)) != 1:
            break
        prefix.append(values[0])
    return tuple(prefix)


def _merge_source_location(blocks: Sequence[ParsedBlock]) -> SourceLocation:
    section_path = _common_section_path(blocks)
    values: dict[str, object] = {"section_path": section_path}
    for start_name, end_name in (
        ("page_start", "page_end"),
        ("paragraph_start", "paragraph_end"),
        ("line_start", "line_end"),
        ("char_start", "char_end"),
    ):
        starts = [getattr(block.source_location, start_name) for block in blocks]
        ends = [getattr(block.source_location, end_name) for block in blocks]
        present_starts = [value for value in starts if value is not None]
        present_ends = [value for value in ends if value is not None]
        if present_starts and present_ends:
            values[start_name] = min(present_starts)
            values[end_name] = max(present_ends)
    return SourceLocation(**values)


def _text_checksum(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class StructureAwareChunker:
    """Create deterministic chunks while preserving structure and source provenance."""

    name = "structure-aware"
    version = "chunker-v1"

    def __init__(self, *, token_counter: TokenCounter, config: ChunkingConfig) -> None:
        self.token_counter = token_counter
        self.config = config

    def chunk(
        self,
        blocks: Sequence[ParsedBlock],
        *,
        document: DocumentRecord,
        cleaner_version: str,
    ) -> tuple[Chunk, ...]:
        """Chunk ordered blocks and enforce a hard token limit on every output."""

        ordered = tuple(sorted(blocks, key=lambda block: block.order))
        self._validate_blocks(ordered, document)
        drafts = self._build_drafts(ordered)
        parser_versions = {block.parser_version for block in ordered}
        parser_version = next(iter(parser_versions), document.parser_version or "unknown-parser")

        chunks: list[Chunk] = []
        for index, draft in enumerate(drafts):
            text = draft.text.strip()
            if not text:
                continue
            token_count = self.token_counter.count(text)
            if token_count > self.config.max_tokens:
                raise ChunkingError(
                    f"chunk exceeds max_tokens after splitting: {token_count} > "
                    f"{self.config.max_tokens}"
                )
            checksum = _text_checksum(text)
            identity = "\x1f".join(
                (
                    document.document_id,
                    document.document_version,
                    str(index),
                    checksum,
                    self.version,
                )
            )
            chunk_id = f"chunk-{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"
            section_path = _common_section_path(draft.blocks)
            chunks.append(
                Chunk(
                    tenant_id=document.tenant_id,
                    document_id=document.document_id,
                    document_version=document.document_version,
                    chunk_id=chunk_id,
                    text=text,
                    text_checksum=checksum,
                    source_location=_merge_source_location(draft.blocks),
                    title=document.title,
                    source_uri=document.source_uri,
                    document_type=document.document_type,
                    industry=document.industry,
                    products=document.products,
                    language=document.language,
                    published_at=document.published_at,
                    active=document.active,
                    confidentiality=document.confidentiality,
                    section_path=section_path,
                    chunk_index=index,
                    parser_version=parser_version,
                    cleaner_version=cleaner_version,
                    chunker_version=self.version,
                    content_checksum=document.content_checksum,
                )
            )
        return tuple(chunks)

    def _validate_blocks(
        self,
        blocks: Sequence[ParsedBlock],
        document: DocumentRecord,
    ) -> None:
        for block in blocks:
            if (
                block.document_id != document.document_id
                or block.document_version != document.document_version
            ):
                raise ChunkingError("parsed block identity does not match document")
        if len({block.order for block in blocks}) != len(blocks):
            raise ChunkingError("parsed block order values must be unique")
        if len({block.parser_version for block in blocks}) > 1:
            raise ChunkingError("one document version cannot mix parser versions")

    def _build_drafts(self, blocks: Sequence[ParsedBlock]) -> tuple[_ChunkDraft, ...]:
        drafts: list[_ChunkDraft] = []
        pending: list[ParsedBlock] = []
        pending_texts: list[str] = []
        current_top_level: str | None = None

        def flush() -> None:
            if pending:
                drafts.append(_ChunkDraft("\n\n".join(pending_texts), tuple(pending)))
                pending.clear()
                pending_texts.clear()

        for block in blocks:
            top_level = _section_path(block)[0] if _section_path(block) else None
            if (
                pending
                and not self.config.allow_cross_top_level_sections
                and top_level != current_top_level
            ):
                flush()

            payloads = self._block_payloads(block)
            if len(payloads) > 1:
                flush()
                drafts.extend(_ChunkDraft(payload, (block,)) for payload in payloads)
                current_top_level = top_level
                continue

            text = payloads[0]
            candidate = "\n\n".join((*pending_texts, text))
            if pending and self.token_counter.count(candidate) > self.config.target_tokens:
                flush()
            pending.append(block)
            pending_texts.append(text)
            current_top_level = top_level
        flush()
        return tuple(drafts)

    def _block_payloads(self, block: ParsedBlock) -> tuple[str, ...]:
        text = block.text.strip()
        if not text:
            return ()
        if self.token_counter.count(text) <= self.config.max_tokens:
            return (text,)
        if block.block_type is BlockType.TABLE:
            return self._split_table(text)
        if block.block_type is BlockType.LIST:
            return self._split_lines(text)
        return self._split_with_overlap(text)

    def _split_with_overlap(self, text: str) -> tuple[str, ...]:
        units: list[str] = []
        for sentence in self._sentence_units(text):
            if self.token_counter.count(sentence) <= self.config.max_tokens:
                units.append(sentence)
            else:
                units.extend(self._split_oversized_unit(sentence, self.config.max_tokens))

        payload_limit = self.config.max_tokens - self.config.overlap_tokens
        windows = self._pack_units(units, payload_limit, " ", allow_oversized_limit=True)
        output: list[str] = []
        previous: tuple[str, ...] = ()
        for window in windows:
            overlap = self._trailing_overlap(previous)
            candidate_units = (*overlap, *window)
            candidate = " ".join(candidate_units).strip()
            while overlap and self.token_counter.count(candidate) > self.config.max_tokens:
                overlap = overlap[1:]
                candidate = " ".join((*overlap, *window)).strip()
            output.append(candidate)
            previous = window
        return tuple(output)

    def _split_lines(self, text: str) -> tuple[str, ...]:
        units: list[str] = []
        for line in (line.strip() for line in text.splitlines()):
            if not line:
                continue
            units.extend(self._split_oversized_unit(line, self.config.max_tokens))
        return tuple(
            "\n".join(window) for window in self._pack_units(units, self.config.max_tokens, "\n")
        )

    def _split_table(self, text: str) -> tuple[str, ...]:
        rows = tuple(line.strip() for line in text.splitlines() if line.strip())
        if len(rows) < 2:
            return self._split_lines(text)
        header, body_rows = rows[0], rows[1:]
        header_tokens = self.token_counter.count(header)
        if header_tokens >= self.config.max_tokens:
            raise IndivisibleTokenError(header, header_tokens, self.config.max_tokens - 1)
        row_limit = self.config.max_tokens - header_tokens
        split_rows: list[str] = []
        for row in body_rows:
            split_rows.extend(self._split_oversized_unit(row, row_limit))
        windows = self._pack_units(split_rows, row_limit, "\n")
        return tuple("\n".join((header, *window)) for window in windows)

    def _pack_units(
        self,
        units: Sequence[str],
        limit: int,
        separator: str,
        *,
        allow_oversized_limit: bool = False,
    ) -> tuple[tuple[str, ...], ...]:
        windows: list[tuple[str, ...]] = []
        current: list[str] = []
        for unit in units:
            unit_tokens = self.token_counter.count(unit)
            if unit_tokens > limit and not allow_oversized_limit:
                raise IndivisibleTokenError(unit, unit_tokens, limit)
            candidate = separator.join((*current, unit))
            if current and self.token_counter.count(candidate) > limit:
                windows.append(tuple(current))
                current = []
            current.append(unit)
        if current:
            windows.append(tuple(current))
        return tuple(windows)

    def _trailing_overlap(self, units: Sequence[str]) -> tuple[str, ...]:
        if not units or self.config.overlap_tokens == 0:
            return ()
        selected: list[str] = []
        for unit in reversed(units):
            candidate = " ".join((unit, *selected))
            if self.token_counter.count(candidate) > self.config.overlap_tokens:
                break
            selected.insert(0, unit)
        return tuple(selected)

    def _split_oversized_unit(self, text: str, limit: int) -> tuple[str, ...]:
        if self.token_counter.count(text) <= limit:
            return (text.strip(),)
        output: list[str] = []
        current = ""
        for piece in _ATOMIC_PATTERN.findall(text):
            candidate = f"{current}{piece}".strip()
            if candidate and self.token_counter.count(candidate) <= limit:
                current = f"{current}{piece}"
                continue
            if current.strip():
                output.append(current.strip())
                current = piece.lstrip()
            else:
                piece_tokens = self.token_counter.count(piece.strip())
                raise IndivisibleTokenError(piece.strip(), piece_tokens, limit)
            if current.strip() and self.token_counter.count(current.strip()) > limit:
                piece_tokens = self.token_counter.count(current.strip())
                raise IndivisibleTokenError(current.strip(), piece_tokens, limit)
        if current.strip():
            output.append(current.strip())
        return tuple(output)

    @staticmethod
    def _sentence_units(text: str) -> tuple[str, ...]:
        units: list[str] = []
        start = 0
        for index, character in enumerate(text):
            next_character = text[index + 1] if index + 1 < len(text) else ""
            is_boundary = character == "\n" or (
                character in _SENTENCE_END
                and (character in "。！？" or not next_character or next_character.isspace())
            )
            if is_boundary:
                unit = text[start : index + 1].strip()
                if unit:
                    units.append(unit)
                start = index + 1
        remainder = text[start:].strip()
        if remainder:
            units.append(remainder)
        return tuple(units)


class CleaningChunkingPipeline:
    """Run conservative cleaning before an injected chunking strategy."""

    def __init__(self, cleaner: TextCleaner, chunker: ChunkingStrategy) -> None:
        self.cleaner = cleaner
        self.chunker = chunker

    def process(
        self,
        blocks: Sequence[ParsedBlock],
        *,
        document: DocumentRecord,
    ) -> tuple[Chunk, ...]:
        cleaned = self.cleaner.clean(blocks)
        return tuple(
            self.chunker.chunk(
                cleaned,
                document=document,
                cleaner_version=self.cleaner.version,
            )
        )
