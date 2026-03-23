"""
Local embedding service — sentence-transformers on CPU.
GPU support via device="cuda" when available.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from sentence_transformers import SentenceTransformer

# Default model: fast, high-quality, 384-dim
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"
FALLBACK_MODEL = "all-MiniLM-L6-v2"

# Cache embeddings to disk to avoid recomputing
CACHE_DIR = Path("~/.openclaw/cache/embeddings").expanduser()
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class Embedder:
    """Local embedding generator using sentence-transformers."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        device: Optional[str] = None,
        dim: Optional[int] = None,
    ):
        """
        Args:
            model_name: HuggingFace model ID
            device: "cpu", "cuda", or None (auto-detect)
            dim: Override embedding dimension (for schema compatibility)
        """
        self.model_name = model_name

        if device is None:
            device = "cuda" if os.environ.get("CUDA_VISIBLE_DEVICES") else "cpu"
        self.device = device

        print(f"Loading embedding model '{model_name}' on {device}...")
        try:
            self.model = SentenceTransformer(model_name, device=device)
        except Exception:
            print(f"⚠️  Failed to load '{model_name}', falling back to '{FALLBACK_MODEL}'")
            self.model_name = FALLBACK_MODEL
            self.model = SentenceTransformer(FALLBACK_MODEL, device=device)

        self._dim = self.model.get_sentence_embedding_dimension()
        if dim and dim != self._dim:
            print(f"⚠️  Model outputs {self._dim}-dim, schema expects {dim}")
        self.dim = dim or self._dim

        print(f"✅ Embedder ready — model={self.model_name}, dim={self.dim}, device={self.device}")

    def encode(self, texts: List[str], normalize: bool = True) -> List[List[float]]:
        """
        Encode texts to embedding vectors.

        Args:
            texts: List of strings to embed
            normalize: L2-normalize vectors (recommended for cosine similarity)

        Returns:
            List of embedding vectors (list of floats)
        """
        if not texts:
            return []

        embeddings = self.model.encode(
            texts,
            normalize_embeddings=normalize,
            batch_size=32,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        return [row.tolist() for row in embeddings]

    def encode_one(self, text: str, normalize: bool = True) -> List[float]:
        """Encode a single text."""
        return self.encode([text], normalize=normalize)[0]


# Singleton instance (lazy-loaded)
_embedder: Optional[Embedder] = None


def get_embedder() -> Embedder:
    """Get or create the singleton Embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = Embedder()
    return _embedder


def encode_texts(texts: List[str], **kwargs) -> List[List[float]]:
    """Convenience: encode texts using the singleton embedder."""
    return get_embedder().encode(texts, **kwargs)


def encode_one(text: str, **kwargs) -> List[float]:
    """Convenience: encode one text using the singleton embedder."""
    return get_embedder().encode_one(text, **kwargs)
