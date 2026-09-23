from __future__ import annotations

from app.domain.models import IngestionErrorCode


class ParserError(RuntimeError):
    """A typed parser failure that can be recorded per document."""

    def __init__(
        self,
        message: str,
        *,
        code: IngestionErrorCode = IngestionErrorCode.PARSE_FAILED,
    ) -> None:
        super().__init__(message)
        self.code = code


class NeedsOCR(ParserError):
    """Raised when a PDF has no extractable text and requires a later OCR task."""

    def __init__(self, message: str = "document contains no extractable text") -> None:
        super().__init__(message, code=IngestionErrorCode.NEEDS_OCR)
