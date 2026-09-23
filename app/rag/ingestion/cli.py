from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient

from app.core.settings import Settings
from app.rag.chunking import ChunkingConfig, StructureAwareChunker
from app.rag.cleaning import ConservativeTextCleaner
from app.rag.embeddings import SentenceTransformerEmbeddingProvider, SentenceTransformerTokenCounter
from app.rag.ingestion.discovery import FileDiscovery
from app.rag.ingestion.manifest import ManifestStore
from app.rag.ingestion.pipeline import DocumentMetadata, IngestionPipeline
from app.rag.vector_store.qdrant import QdrantVectorStore


def _metadata(path: Path) -> dict[str, DocumentMetadata]:
    raw: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("metadata manifest must be a JSON object keyed by relative path")
    return {
        relative_path: DocumentMetadata.model_validate(value)
        for relative_path, value in raw.items()
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest approved documents into Qdrant.")
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=Path("data/processed/manifest.jsonl"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    settings = Settings()
    if not settings.embedding_model or not settings.embedding_model_revision:
        print(
            "Set EMBEDDING_MODEL, EMBEDDING_MODEL_REVISION, and EMBEDDING_DIMENSION.",
            file=sys.stderr,
        )
        return 2
    if settings.embedding_dimension is None:
        print("Set EMBEDDING_DIMENSION.", file=sys.stderr)
        return 2
    api_key = settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None
    try:
        client = QdrantClient(
            url=settings.qdrant_url,
            api_key=api_key,
            trust_env=False,
            check_compatibility=False,
        )
        provider = SentenceTransformerEmbeddingProvider(
            model_name=settings.embedding_model,
            model_revision=settings.embedding_model_revision,
        )
        if provider.dimension != settings.embedding_dimension:
            raise ValueError(
                f"model dimension {provider.dimension} does not match configured "
                f"{settings.embedding_dimension}"
            )
        store = QdrantVectorStore(
            client,
            collection_name=settings.qdrant_collection,
            model_name=settings.embedding_model,
            model_revision=settings.embedding_model_revision,
            dimension=settings.embedding_dimension,
            tenant_id=settings.tenant_id,
        )
        discovery = FileDiscovery(
            args.data_root,
            max_file_size_bytes=settings.max_file_size_mb * 1024 * 1024,
        )
        chunker = StructureAwareChunker(
            token_counter=SentenceTransformerTokenCounter(provider),
            config=ChunkingConfig(
                target_tokens=settings.chunk_target_tokens,
                max_tokens=settings.chunk_max_tokens,
                overlap_tokens=settings.chunk_overlap_tokens,
                allow_cross_top_level_sections=settings.chunk_allow_cross_top_level_sections,
            ),
        )
        pipeline = IngestionPipeline(
            discovery=discovery,
            manifest=ManifestStore(args.manifest),
            vector_store=store,
            embedding_provider=provider,
            cleaner=ConservativeTextCleaner(),
            chunker=chunker,
        )
        summary = pipeline.run(_metadata(args.metadata))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Ingestion could not start: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
