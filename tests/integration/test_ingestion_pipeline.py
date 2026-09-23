from __future__ import annotations

import hashlib
from pathlib import Path

from qdrant_client import QdrantClient

from app.domain.models import (
    Confidentiality,
    DocumentType,
    EmbeddingBatch,
    Language,
)
from app.rag.embeddings import EmbeddingProviderError
from app.rag.ingestion.discovery import FileDiscovery
from app.rag.ingestion.manifest import ManifestStatus, ManifestStore
from app.rag.ingestion.pipeline import DocumentMetadata, IngestionPipeline
from app.rag.vector_store.qdrant import QdrantVectorStore


class FakeEmbeddingProvider:
    model_name = "test-model"
    model_revision = "test-revision"
    dimension = 3

    def __init__(self) -> None:
        self.fail = False

    def embed(self, texts, *, chunk_ids) -> EmbeddingBatch:
        if self.fail:
            raise EmbeddingProviderError("synthetic embedding failure")
        return EmbeddingBatch(
            model_name=self.model_name,
            model_revision=self.model_revision,
            dimension=self.dimension,
            chunk_ids=tuple(chunk_ids),
            vectors=tuple((1.0, 0.0, 0.0) for _ in texts),
            normalized=True,
        )


def _metadata() -> DocumentMetadata:
    return DocumentMetadata(
        title="Synthetic guide",
        document_type=DocumentType.PRODUCT_GUIDE,
        confidentiality=Confidentiality.SYNTHETIC,
        industry=("finance",),
        products=("agent-x",),
        language=Language.EN,
    )


def _pipeline(root: Path, tmp_path: Path, provider: FakeEmbeddingProvider):
    manifest = ManifestStore(tmp_path / "manifest.jsonl")
    store = QdrantVectorStore(
        QdrantClient(":memory:"),
        collection_name=f"test-{hashlib.sha256(str(tmp_path).encode()).hexdigest()[:8]}",
        model_name=provider.model_name,
        model_revision=provider.model_revision,
        dimension=provider.dimension,
    )
    pipeline = IngestionPipeline(
        discovery=FileDiscovery(root, max_file_size_bytes=1024 * 1024),
        manifest=manifest,
        vector_store=store,
        embedding_provider=provider,
    )
    return pipeline, store, manifest


def test_ingestion_pipeline_skips_unchanged_and_activates_changed_version(
    tmp_path: Path,
) -> None:
    root = tmp_path / "documents"
    root.mkdir()
    source = root / "guide.txt"
    source.write_text("Finance product guide. Keep 99% availability.", encoding="utf-8")
    provider = FakeEmbeddingProvider()
    pipeline, store, manifest = _pipeline(root, tmp_path, provider)
    metadata = {"guide.txt": _metadata()}

    first = pipeline.run(metadata)
    second = pipeline.run(metadata)

    assert (first.parsed, first.upserted, first.failed) == (1, 1, 0)
    assert (second.skipped, second.upserted, second.failed) == (1, 0, 0)
    versions = manifest.load()
    assert len(versions) == 1
    assert versions[0].status is ManifestStatus.ACTIVE
    assert store.count(tenant_id="demo", active_only=True) == 1

    source.write_text("Finance product guide. Keep 99.5% availability.", encoding="utf-8")
    changed = pipeline.run(metadata)

    assert (changed.upserted, changed.failed) == (1, 0)
    versions = manifest.load()
    assert len(versions) == 2
    assert sum(entry.status is ManifestStatus.ACTIVE for entry in versions) == 1
    assert store.count(tenant_id="demo", active_only=True) == 1


def test_failed_replacement_leaves_previous_version_active(tmp_path: Path) -> None:
    root = tmp_path / "documents"
    root.mkdir()
    source = root / "guide.txt"
    source.write_text("Initial stable guide.", encoding="utf-8")
    provider = FakeEmbeddingProvider()
    pipeline, store, manifest = _pipeline(root, tmp_path, provider)
    metadata = {"guide.txt": _metadata()}
    assert pipeline.run(metadata).failed == 0
    old_entry = manifest.load()[0]

    source.write_text("Changed replacement content.", encoding="utf-8")
    provider.fail = True
    failed = pipeline.run(metadata)

    assert failed.failed == 1
    assert (
        store.count(
            tenant_id="demo",
            filters={
                "document_id": old_entry.document_id,
                "document_version": old_entry.document_version,
            },
            active_only=True,
        )
        == 1
    )
    latest = manifest.get(old_entry.document_id)
    assert latest is not None
    assert latest.status is ManifestStatus.FAILED


def test_pipeline_isolates_corrupt_document_from_valid_document(tmp_path: Path) -> None:
    root = tmp_path / "documents"
    root.mkdir()
    (root / "valid.txt").write_text("Valid synthetic evidence.", encoding="utf-8")
    (root / "broken.pdf").write_bytes(b"not a PDF")
    provider = FakeEmbeddingProvider()
    pipeline, store, _ = _pipeline(root, tmp_path, provider)
    metadata = {"valid.txt": _metadata(), "broken.pdf": _metadata()}

    summary = pipeline.run(metadata)

    assert summary.parsed == 1
    assert summary.upserted == 1
    assert summary.failed == 1
    assert store.count(tenant_id="demo", active_only=True) == 1
