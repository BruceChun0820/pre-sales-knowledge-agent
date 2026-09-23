from __future__ import annotations

import re
from pathlib import Path

from app.domain.models import BlockType, DocumentRecord, ParsedBlock, SourceLocation

from .errors import ParserError

_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_LIST_PATTERN = re.compile(r"^(?:[-*+]\s+|\d+[.)]\s+)")


def _read_utf8(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ParserError(f"unable to read UTF-8 text: {exc}") from exc


def _block(
    lines: list[str],
    *,
    start_line: int,
    end_line: int,
    document: DocumentRecord,
    order: int,
    block_type: BlockType,
    section_path: tuple[str, ...],
    parser_name: str,
    parser_version: str,
) -> ParsedBlock:
    text = "\n".join(lines).strip()
    return ParsedBlock(
        document_id=document.document_id,
        document_version=document.document_version,
        block_id=f"{document.document_id}-block-{order:04d}",
        block_type=block_type,
        text=text,
        source_location=SourceLocation(line_start=start_line, line_end=end_line),
        order=order,
        parser_name=parser_name,
        parser_version=parser_version,
        section_path=section_path,
    )


class TextParser:
    """Parse plain text paragraphs while preserving 1-based line ranges."""

    name = "text"
    version = "text-v1"

    def parse(self, path: Path, *, document: DocumentRecord) -> tuple[ParsedBlock, ...]:
        lines = _read_utf8(path)
        blocks: list[ParsedBlock] = []
        current: list[str] = []
        start_line: int | None = None

        def flush(end_line: int) -> None:
            nonlocal current, start_line
            if current and start_line is not None:
                is_list = all(_LIST_PATTERN.match(line.strip()) for line in current)
                block_type = BlockType.LIST if is_list else BlockType.PARAGRAPH
                blocks.append(
                    _block(
                        current,
                        start_line=start_line,
                        end_line=end_line,
                        document=document,
                        order=len(blocks),
                        block_type=block_type,
                        section_path=(),
                        parser_name=self.name,
                        parser_version=self.version,
                    )
                )
            current = []
            start_line = None

        for line_number, line in enumerate(lines, start=1):
            if not line.strip():
                if start_line is not None:
                    flush(line_number - 1)
                continue
            if start_line is None:
                start_line = line_number
            current.append(line)
        if start_line is not None:
            flush(len(lines))
        return tuple(blocks)


class MarkdownParser(TextParser):
    """Parse Markdown headings, paragraphs, lists, and pipe tables."""

    name = "markdown"
    version = "markdown-v1"

    def parse(self, path: Path, *, document: DocumentRecord) -> tuple[ParsedBlock, ...]:
        lines = _read_utf8(path)
        blocks: list[ParsedBlock] = []
        sections: list[tuple[int, str]] = []
        current: list[str] = []
        start_line: int | None = None

        def current_section_path() -> tuple[str, ...]:
            return tuple(title for _, title in sections)

        def flush(end_line: int) -> None:
            nonlocal current, start_line
            if not current or start_line is None:
                current = []
                start_line = None
                return
            stripped = [line.strip() for line in current]
            if all(line.startswith("|") for line in stripped):
                block_type = BlockType.TABLE
            elif all(_LIST_PATTERN.match(line) for line in stripped):
                block_type = BlockType.LIST
            else:
                block_type = BlockType.PARAGRAPH
            blocks.append(
                _block(
                    current,
                    start_line=start_line,
                    end_line=end_line,
                    document=document,
                    order=len(blocks),
                    block_type=block_type,
                    section_path=current_section_path(),
                    parser_name=self.name,
                    parser_version=self.version,
                )
            )
            current = []
            start_line = None

        for line_number, line in enumerate(lines, start=1):
            heading = _HEADING_PATTERN.match(line.strip())
            if heading:
                if start_line is not None:
                    flush(line_number - 1)
                level = len(heading.group(1))
                title = heading.group(2).strip()
                sections = [(depth, value) for depth, value in sections if depth < level]
                sections.append((level, title))
                blocks.append(
                    _block(
                        [title],
                        start_line=line_number,
                        end_line=line_number,
                        document=document,
                        order=len(blocks),
                        block_type=BlockType.HEADING,
                        section_path=current_section_path(),
                        parser_name=self.name,
                        parser_version=self.version,
                    )
                )
                continue
            if not line.strip():
                if start_line is not None:
                    flush(line_number - 1)
                continue
            if start_line is None:
                start_line = line_number
            current.append(line)
        if start_line is not None:
            flush(len(lines))
        return tuple(blocks)
