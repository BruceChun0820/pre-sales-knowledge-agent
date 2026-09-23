from __future__ import annotations

import pytest

from app.rag.embeddings import (
    EmbeddingProviderError,
    SentenceTransformerEmbeddingProvider,
    SentenceTransformerTokenCounter,
)


class FakeArray:
    def __init__(self, values: list[list[float]]) -> None:
        self.values = values

    def tolist(self) -> list[list[float]]:
        return self.values


class FakeTokenizer:
    def __call__(self, text: str, **_: object) -> dict[str, list[int]]:
        return {"input_ids": list(range(len(text.split()) + 2))}


class FakeModel:
    max_seq_length = 128
    tokenizer = FakeTokenizer()

    def get_embedding_dimension(self) -> int:
        return 2

    def encode_document(self, texts: list[str], **_: object) -> FakeArray:
        return FakeArray([[float(len(text)), 1.0] for text in texts])

    def encode_query(self, texts: list[str], **_: object) -> FakeArray:
        return FakeArray([[1.0, float(len(text))] for text in texts])


def test_sentence_transformer_adapter_returns_versioned_embedding_batch() -> None:
    provider = SentenceTransformerEmbeddingProvider(
        model_name="fake/model",
        model_revision="revision-1",
        model=FakeModel(),
        batch_size=2,
    )

    batch = provider.embed(("alpha", "beta"), chunk_ids=("c1", "c2"))

    assert batch.model_name == "fake/model"
    assert batch.model_revision == "revision-1"
    assert batch.dimension == 2
    assert batch.chunk_ids == ("c1", "c2")
    assert batch.vectors == ((5.0, 1.0), (4.0, 1.0))
    assert batch.normalized is True
    assert provider.max_sequence_length == 128
    assert provider.count_tokens("one two") == 4
    assert SentenceTransformerTokenCounter(provider).count("one two") == 4
    assert provider.embed_queries(("query",)) == ((1.0, 5.0),)


def test_sentence_transformer_adapter_rejects_mismatched_inputs() -> None:
    provider = SentenceTransformerEmbeddingProvider(
        model_name="fake/model",
        model_revision="revision-1",
        model=FakeModel(),
    )

    with pytest.raises(ValueError, match="same length"):
        provider.embed(("alpha",), chunk_ids=("c1", "c2"))


class BrokenModel(FakeModel):
    def encode_document(self, texts: list[str], **_: object) -> FakeArray:
        raise RuntimeError("synthetic failure")


def test_sentence_transformer_adapter_exposes_encoding_failure() -> None:
    provider = SentenceTransformerEmbeddingProvider(
        model_name="fake/model",
        model_revision="revision-1",
        model=BrokenModel(),
    )

    with pytest.raises(EmbeddingProviderError, match="synthetic failure"):
        provider.embed(("alpha",), chunk_ids=("c1",))
