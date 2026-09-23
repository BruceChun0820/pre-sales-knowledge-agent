from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Sequence

from app.domain.models import BlockType, ParsedBlock

_HORIZONTAL_WHITESPACE = re.compile(r"[ \t\f\v]+")
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")
_SPLIT_WORD = re.compile(r"(?<=[A-Za-z])-[ \t]*\n[ \t]*(?=[a-z])")
_CJK_LINE_BREAK = re.compile(r"(?<=[\u3400-\u9fff])\n(?=[\u3400-\u9fff])")


class ConservativeTextCleaner:
    """Apply deterministic normalization while preserving source facts and boundaries."""

    name = "conservative"
    version = "cleaner-v1"

    def __init__(
        self, *, repeated_edge_min_pages: int = 3, repeated_edge_max_chars: int = 120
    ) -> None:
        if repeated_edge_min_pages < 2:
            raise ValueError("repeated_edge_min_pages must be at least 2")
        if repeated_edge_max_chars < 1:
            raise ValueError("repeated_edge_max_chars must be positive")
        self.repeated_edge_min_pages = repeated_edge_min_pages
        self.repeated_edge_max_chars = repeated_edge_max_chars

    def clean(self, blocks: Sequence[ParsedBlock]) -> tuple[ParsedBlock, ...]:
        """Normalize blocks and remove only repeated, page-edge header/footer candidates."""

        normalized = tuple(
            block.model_copy(update={"text": self.clean_text(block.text, block.block_type)})
            for block in sorted(blocks, key=lambda item: item.order)
        )
        repeated_edge_ids = self._repeated_page_edge_ids(normalized)
        return tuple(block for block in normalized if block.block_id not in repeated_edge_ids)

    def clean_text(self, text: str, block_type: BlockType) -> str:
        """Normalize Unicode and whitespace without rewriting words or source facts."""

        value = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
        value = _SPLIT_WORD.sub("", value)
        lines = [_HORIZONTAL_WHITESPACE.sub(" ", line).strip() for line in value.split("\n")]
        value = "\n".join(lines)
        value = _EXCESS_BLANK_LINES.sub("\n\n", value).strip()

        if block_type in {BlockType.HEADING, BlockType.PARAGRAPH, BlockType.CAPTION}:
            value = _CJK_LINE_BREAK.sub("", value)
            value = re.sub(r"\n+", " ", value)
            value = _HORIZONTAL_WHITESPACE.sub(" ", value).strip()
        return value

    def _repeated_page_edge_ids(self, blocks: Sequence[ParsedBlock]) -> frozenset[str]:
        page_blocks: dict[int, list[ParsedBlock]] = defaultdict(list)
        for block in blocks:
            location = block.source_location
            if location.page_start is not None and location.page_start == location.page_end:
                page_blocks[location.page_start].append(block)

        occurrences: dict[str, list[ParsedBlock]] = defaultdict(list)
        for blocks_on_page in page_blocks.values():
            if not blocks_on_page:
                continue
            edges = (blocks_on_page[0], blocks_on_page[-1])
            for block in dict.fromkeys(edges):
                if (
                    block.block_type in {BlockType.PARAGRAPH, BlockType.CAPTION}
                    and len(block.text) <= self.repeated_edge_max_chars
                ):
                    occurrences[block.text].append(block)

        return frozenset(
            block.block_id
            for repeated in occurrences.values()
            if len({block.source_location.page_start for block in repeated})
            >= self.repeated_edge_min_pages
            for block in repeated
        )
