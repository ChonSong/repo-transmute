"""Repo Reaper — semantic code indexing and RAG for repositories."""
from repo_reaper.indexer import RepoIndexer, CodeChunk, COLLECTION_NAME, EMBED_DIM
from repo_reaper.rag import search_code, build_context, index_repo, index_all_cached
from repo_reaper.embedder import Embedder, get_embedder, encode_texts, encode_one

__all__ = [
    "RepoIndexer", "CodeChunk", "COLLECTION_NAME", "EMBED_DIM",
    "search_code", "build_context", "index_repo", "index_all_cached",
    "Embedder", "get_embedder", "encode_texts", "encode_one",
]
