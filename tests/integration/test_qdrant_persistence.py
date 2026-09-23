from __future__ import annotations

import hashlib
import os
import subprocess
import uuid
from pathlib import Path

import pytest
from qdrant_client import QdrantClient

from app.domain.models import (
    Chunk,
    Confidentiality,
    DocumentType,
    EmbeddingBatch,
    Language,
    SourceLocation,
)
from app.rag.vector_store import QdrantVectorStore, VectorDimensionMismatchError


@pytest.fixture
def qdrant_collection():
    url = os.environ.get("QDRANT_URL", "http://127.0.0.1:6333")
    client = QdrantClient(url=url, timeout=3, trust_env=False, check_compatibility=False)
    try:
        client.get_collections()
    except Exception as exc:
        client.close()
        pytest.skip(f"Qdrant integration server is unavailable: {exc}")
    name = f"phase1_test_{uuid.uuid4().hex}"
    store = QdrantVectorStore(
        client,
        collection_name=name,
        model_name="integration-model",
        model_revision="integration-revision",
        dimension=3,
    )
    try:
        yield store, name, url
    finally:
        cleanup = QdrantClient(url=url, timeout=5, trust_env=False, check_compatibility=False)
        if cleanup.collection_exists(name):
            cleanup.delete_collection(name)
        cleanup.close()
        client.close()


def _chunk(chunk_id: str, *, active: bool, industry: str, product: str) -> Chunk:
    text = f"Synthetic evidence {chunk_id}"
    digest = hashlib.sha256(text.encode()).hexdigest()
    source_digest = hashlib.sha256(b"synthetic source").hexdigest()
    return Chunk(
        document_id="integration-document",
        document_version="v1",
        chunk_id=chunk_id,
        text=text,
        text_checksum=digest,
        source_location=SourceLocation(page_start=1, page_end=1),
        title="Synthetic test",
        source_uri="synthetic.txt",
        document_type=DocumentType.PRODUCT_GUIDE,
        industry=(industry,),
        products=(product,),
        language=Language.EN,
        active=active,
        confidentiality=Confidentiality.SYNTHETIC,
        section_path=("Overview",),
        chunk_index=0,
        parser_version="parser-v1",
        cleaner_version="cleaner-v1",
        chunker_version="chunker-v1",
        content_checksum=source_digest,
    )


def _upsert(store: QdrantVectorStore, chunk: Chunk) -> None:
    store.upsert(
        (chunk,),
        EmbeddingBatch(
            model_name="integration-model",
            model_revision="integration-revision",
            dimension=3,
            chunk_ids=(chunk.chunk_id,),
            vectors=((1.0, 0.0, 0.0),),
            normalized=True,
        ),
    )


def test_qdrant_server_filters_and_deterministic_upsert(qdrant_collection) -> None:
    store, _, _ = qdrant_collection
    expected = _chunk("visible", active=True, industry="finance", product="agent-x")
    _upsert(store, expected)
    _upsert(store, expected)
    _upsert(store, _chunk("inactive", active=False, industry="finance", product="agent-x"))
    _upsert(store, _chunk("other-industry", active=True, industry="healthcare", product="agent-x"))
    _upsert(store, _chunk("other-product", active=True, industry="finance", product="agent-y"))

    assert store.count(tenant_id="demo") == 4
    filters = (
        {"industry": "finance"},
        {"document_type": "product_guide"},
        {"products": "agent-x"},
    )
    for query_filter in filters:
        found = store.search((1.0, 0.0, 0.0), tenant_id="demo", limit=10, filters=query_filter)
        assert "inactive" not in {chunk.chunk_id for chunk in found}
    assert [
        chunk.chunk_id
        for chunk in store.search(
            (1.0, 0.0, 0.0),
            tenant_id="demo",
            limit=10,
            filters={"industry": "finance", "products": "agent-x"},
        )
    ] == ["visible"]
    with pytest.raises(VectorDimensionMismatchError):
        store.search((1.0, 0.0), tenant_id="demo", limit=1)


def test_qdrant_server_data_survives_compose_restart(qdrant_collection) -> None:
    store, collection_name, url = qdrant_collection
    chunk = _chunk("survives-restart", active=True, industry="finance", product="agent-x")
    _upsert(store, chunk)
    compose_file = Path(__file__).parents[2] / "infra" / "docker-compose.yml"
    subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "restart", "qdrant"],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )

    subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "60",
            "qdrant",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=70,
    )
    reopened = QdrantVectorStore(
        QdrantClient(url=url, timeout=10, trust_env=False, check_compatibility=False),
        collection_name=collection_name,
        model_name="integration-model",
        model_revision="integration-revision",
        dimension=3,
    )
    assert reopened.count(tenant_id="demo", active_only=True) == 1
    assert reopened.search((1.0, 0.0, 0.0), tenant_id="demo", limit=1)[0].chunk_id == chunk.chunk_id
