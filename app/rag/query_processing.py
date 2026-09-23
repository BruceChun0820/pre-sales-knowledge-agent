from __future__ import annotations

import unicodedata


class QueryProcessor:
    """Apply deterministic, meaning-preserving normalization without query expansion."""

    def normalize(self, query: str) -> str:
        """Trim and Unicode-normalize a query while preserving tokens and punctuation."""
        return unicodedata.normalize("NFKC", query).strip()
