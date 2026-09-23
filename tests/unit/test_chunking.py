from __future__ import annotations

import pytest

from app.domain.models import (
    BlockType,
    Confidentiality,
    DocumentRecord,
    DocumentType,
    ParsedBlock,
    SourceLocation,
)
from app.rag.chunking import (
    ChunkingConfig,
    CleaningChunkingPipeline,
    IndivisibleTokenError,
    RegexTokenCounter,
    StructureAwareChunker,
)
from app.rag.cleaning import ConservativeTextCleaner

CHECKSUM = "a" * 64


def make_document() -> DocumentRecord:
    return DocumentRecord(
        document_id="doc-chunking",
        document_version="sha256-test",
        title="Synthetic chunking guide",
        source_uri="fixtures/chunking.md",
        document_type=DocumentType.PRODUCT_GUIDE,
        industry=("technology",),
        products=("X-200",),
        confidentiality=Confidentiality.SYNTHETIC,
        content_checksum=CHECKSUM,
    )


def make_block(
    order: int,
    text: str,
    *,
    block_type: BlockType = BlockType.PARAGRAPH,
    section_path: tuple[str, ...] = ("Overview",),
    page: int | None = None,
) -> ParsedBlock:
    location = (
        SourceLocation(page_start=page, page_end=page)
        if page is not None
        else SourceLocation(line_start=order * 2 + 1, line_end=order * 2 + 2)
    )
    return ParsedBlock(
        document_id="doc-chunking",
        document_version="sha256-test",
        block_id=f"block-{order}",
        block_type=block_type,
        text=text,
        source_location=location,
        order=order,
        parser_name="markdown",
        parser_version="markdown-v1",
        section_path=section_path,
    )


def make_pipeline(config: ChunkingConfig) -> CleaningChunkingPipeline:
    return CleaningChunkingPipeline(
        ConservativeTextCleaner(),
        StructureAwareChunker(token_counter=RegexTokenCounter(), config=config),
    )


def test_cleaner_preserves_numbers_models_negation_and_limitations() -> None:
    raw = "型号 X-200 支持 99.9%，但不支持自动扩容，仅限 EU。\nlimi-\ntation applies."

    cleaned = ConservativeTextCleaner().clean((make_block(0, raw),))

    assert (
        cleaned[0].text == "型号 X-200 支持 99.9%，但不支持自动扩容，仅限 EU。 limitation applies."
    )
    for critical_value in ("X-200", "99.9%", "不支持", "仅限", "limitation"):
        assert critical_value in cleaned[0].text


def test_cleaner_removes_only_repeated_page_edge_headers() -> None:
    blocks: list[ParsedBlock] = []
    for page in range(1, 4):
        blocks.append(make_block((page - 1) * 2, "Synthetic Guide", page=page))
        blocks.append(make_block((page - 1) * 2 + 1, f"Body page {page}.", page=page))

    cleaned = ConservativeTextCleaner().clean(blocks)

    assert [block.text for block in cleaned] == [
        "Body page 1.",
        "Body page 2.",
        "Body page 3.",
    ]


def test_chunking_is_deterministic_and_propagates_metadata_and_source_range() -> None:
    blocks = (
        make_block(0, "Product X-200 supports controlled rollout."),
        make_block(1, "It does not support unlimited expansion."),
    )
    pipeline = make_pipeline(ChunkingConfig(target_tokens=32, max_tokens=32, overlap_tokens=4))

    first = pipeline.process(blocks, document=make_document())
    second = pipeline.process(blocks, document=make_document())

    assert [(chunk.chunk_id, chunk.text_checksum) for chunk in first] == [
        (chunk.chunk_id, chunk.text_checksum) for chunk in second
    ]
    assert len(first) == 1
    assert first[0].source_location.line_start == 1
    assert first[0].source_location.line_end == 4
    assert first[0].section_path == ("Overview",)
    assert first[0].cleaner_version == "cleaner-v1"
    assert first[0].chunker_version == "chunker-v1"
    assert first[0].parser_version == "markdown-v1"
    assert first[0].products == ("X-200",)


def test_chunker_does_not_cross_top_level_sections_by_default() -> None:
    blocks = (
        make_block(0, "Section A", block_type=BlockType.HEADING, section_path=("A",)),
        make_block(1, "Details for A.", section_path=("A",)),
        make_block(2, "Section B", block_type=BlockType.HEADING, section_path=("B",)),
        make_block(3, "Details for B.", section_path=("B",)),
    )
    pipeline = make_pipeline(ChunkingConfig(target_tokens=100, max_tokens=100, overlap_tokens=0))

    chunks = pipeline.process(blocks, document=make_document())

    assert len(chunks) == 2
    assert [chunk.section_path for chunk in chunks] == [("A",), ("B",)]
    assert "Section B" not in chunks[0].text


def test_long_paragraph_overlap_uses_complete_sentence_boundaries() -> None:
    block = make_block(0, "Alpha beta. Gamma delta. Epsilon zeta. Eta theta.")
    counter = RegexTokenCounter()
    pipeline = make_pipeline(ChunkingConfig(target_tokens=8, max_tokens=8, overlap_tokens=4))

    chunks = pipeline.process((block,), document=make_document())

    assert len(chunks) == 4
    assert chunks[1].text.startswith("Alpha beta.")
    assert chunks[2].text.startswith("Gamma delta.")
    assert all(counter.count(chunk.text) <= 8 for chunk in chunks)


def test_long_chinese_text_respects_hard_token_limit() -> None:
    block = make_block(0, "甲乙丙丁戊己庚辛壬癸。甲乙丙丁戊己庚辛壬癸。")
    counter = RegexTokenCounter()
    pipeline = make_pipeline(ChunkingConfig(target_tokens=8, max_tokens=8, overlap_tokens=2))

    chunks = pipeline.process((block,), document=make_document())

    assert len(chunks) > 1
    assert all(chunk.text for chunk in chunks)
    assert all(counter.count(chunk.text) <= 8 for chunk in chunks)


def test_long_list_preserves_item_boundaries_and_markers() -> None:
    block = make_block(
        0,
        "- item one\n- item two\n- item three",
        block_type=BlockType.LIST,
    )
    counter = RegexTokenCounter()
    pipeline = make_pipeline(ChunkingConfig(target_tokens=4, max_tokens=4, overlap_tokens=0))

    chunks = pipeline.process((block,), document=make_document())

    assert [chunk.text for chunk in chunks] == ["- item one", "- item two", "- item three"]
    assert all(counter.count(chunk.text) <= 4 for chunk in chunks)


def test_long_table_repeats_header_without_exceeding_limit() -> None:
    block = make_block(
        0,
        "Model | Limit\nX-100 | 10\nX-200 | 20\nX-300 | 30",
        block_type=BlockType.TABLE,
    )
    counter = RegexTokenCounter()
    pipeline = make_pipeline(ChunkingConfig(target_tokens=8, max_tokens=8, overlap_tokens=0))

    chunks = pipeline.process((block,), document=make_document())

    assert len(chunks) == 3
    assert all(chunk.text.startswith("Model | Limit\n") for chunk in chunks)
    assert all(counter.count(chunk.text) <= 8 for chunk in chunks)


class IndivisibleCounter:
    def count(self, text: str) -> int:
        return 10 if "MEGATOKEN" in text else len(text.split())


def test_indivisible_token_is_reported_explicitly() -> None:
    chunker = StructureAwareChunker(
        token_counter=IndivisibleCounter(),
        config=ChunkingConfig(target_tokens=5, max_tokens=5, overlap_tokens=0),
    )

    with pytest.raises(IndivisibleTokenError, match="indivisible token"):
        chunker.chunk(
            (make_block(0, "MEGATOKEN"),),
            document=make_document(),
            cleaner_version="cleaner-v1",
        )
