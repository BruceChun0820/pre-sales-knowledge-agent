from __future__ import annotations

from pathlib import Path

from docx import Document as load_document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.domain.models import BlockType, DocumentRecord, ParsedBlock, SourceLocation

from .errors import ParserError


class DocxParser:
    """Extract paragraphs and tables in document-body order."""

    name = "docx"
    version = "docx-v1"

    def parse(self, path: Path, *, document: DocumentRecord) -> tuple[ParsedBlock, ...]:
        try:
            source_document = load_document(str(path))
            blocks: list[ParsedBlock] = []
            section_path: list[str] = []
            source_index = 0
            for element in source_document.element.body.iterchildren():
                source_index += 1
                if isinstance(element, CT_P):
                    paragraph = Paragraph(element, source_document)
                    text = paragraph.text.strip()
                    if not text:
                        continue
                    style_name = paragraph.style.name if paragraph.style else ""
                    if style_name.startswith("Heading"):
                        block_type = BlockType.HEADING
                        section_path = [*section_path, text]
                    else:
                        block_type = BlockType.PARAGRAPH
                    block_text = text
                elif isinstance(element, CT_Tbl):
                    table = Table(element, source_document)
                    rows = [
                        " | ".join(cell.text.strip() for cell in row.cells) for row in table.rows
                    ]
                    block_text = "\n".join(row for row in rows if row).strip()
                    if not block_text:
                        continue
                    block_type = BlockType.TABLE
                else:
                    continue

                blocks.append(
                    ParsedBlock(
                        document_id=document.document_id,
                        document_version=document.document_version,
                        block_id=f"{document.document_id}-body-{source_index:04d}",
                        block_type=block_type,
                        text=block_text,
                        source_location=SourceLocation(
                            paragraph_start=source_index,
                            paragraph_end=source_index,
                        ),
                        order=len(blocks),
                        parser_name=self.name,
                        parser_version=self.version,
                        section_path=tuple(section_path),
                    )
                )
            return tuple(blocks)
        except Exception as exc:
            raise ParserError(f"unable to parse DOCX {path.name}: {exc}") from exc
