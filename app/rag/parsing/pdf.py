from __future__ import annotations

from pathlib import Path

import pymupdf

from app.domain.models import BlockType, DocumentRecord, ParsedBlock, SourceLocation

from .errors import NeedsOCR, ParserError


class PdfParser:
    """Extract ordered text blocks from digital PDFs with page provenance."""

    name = "pdf"
    version = "pdf-v1"

    def parse(self, path: Path, *, document: DocumentRecord) -> tuple[ParsedBlock, ...]:
        blocks: list[ParsedBlock] = []
        pdf: pymupdf.Document | None = None
        try:
            pdf = pymupdf.open(str(path))
            for page_index, page in enumerate(pdf, start=1):
                for block_index, raw_block in enumerate(page.get_text("blocks")):
                    text = str(raw_block[4]).strip()
                    if not text:
                        continue
                    blocks.append(
                        ParsedBlock(
                            document_id=document.document_id,
                            document_version=document.document_version,
                            block_id=f"{document.document_id}-page-{page_index}-block-{block_index}",
                            block_type=BlockType.PARAGRAPH,
                            text=text,
                            source_location=SourceLocation(
                                page_start=page_index,
                                page_end=page_index,
                            ),
                            order=len(blocks),
                            parser_name=self.name,
                            parser_version=self.version,
                        )
                    )
        except NeedsOCR:
            raise
        except Exception as exc:
            raise ParserError(f"unable to parse PDF {path.name}: {exc}") from exc
        finally:
            if pdf is not None:
                pdf.close()

        if not blocks:
            raise NeedsOCR()
        return tuple(blocks)
