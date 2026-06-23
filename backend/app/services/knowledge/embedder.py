"""Embedding provider abstraction.

The default ``mock`` embedder is deterministic (hash-seeded pseudo-vector) so the
RAG pipeline runs offline with no API key. ``local`` uses fastembed (ONNX, no
torch) with a lightweight multilingual model — real semantic search, offline,
no external key. ``openai`` calls the OpenAI embeddings API. Vector dimension
always matches settings.embedding_dim.
"""
from __future__ import annotations

import hashlib
import math
from functools import lru_cache

from app.core.config import settings


@lru_cache(maxsize=2)
def _local_model(model_name: str):
    """Cache the fastembed model (downloads weights to local cache on first use)."""
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=model_name)


def _mock_embed(text: str, dim: int) -> list[float]:
    """Deterministic unit vector seeded from the text hash."""
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    vals: list[float] = []
    i = 0
    while len(vals) < dim:
        h = hashlib.sha256(seed + i.to_bytes(4, "big")).digest()
        for b in h:
            if len(vals) >= dim:
                break
            vals.append((b / 255.0) * 2 - 1)  # [-1, 1]
        i += 1
    norm = math.sqrt(sum(v * v for v in vals)) or 1.0
    return [v / norm for v in vals]


def embed_text(text: str) -> list[float]:
    dim = settings.embedding_dim
    if settings.embedding_provider == "mock":
        return _mock_embed(text, dim)
    if settings.embedding_provider == "local":
        model = _local_model(settings.embedding_model)
        vec = next(iter(model.embed([text])))
        return [float(x) for x in vec]
    if settings.embedding_provider == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        resp = client.embeddings.create(model=settings.embedding_model, input=text)
        return resp.data[0].embedding
    raise ValueError(f"unknown embedding provider: {settings.embedding_provider}")
