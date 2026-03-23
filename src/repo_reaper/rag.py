"""
RAG query interface for Repo Reaper.
Provides clean wrappers for semantic code search and context building.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Optional

from repo_reaper.indexer import RepoIndexer, CodeChunk


def search_code(
    query: str,
    repo: Optional[str] = None,
    lang: Optional[str] = None,
    top_k: int = 5,
    embedder_device: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Semantic search across indexed code repositories.

    Args:
        query: Natural language query (e.g., "agent loop implementation")
        repo: Filter by repo name (e.g., "HKUDS/nanobot")
        lang: Filter by language ("python", "typescript")
        top_k: Number of results

    Returns:
        List of code chunks with similarity scores
    """
    indexer = RepoIndexer(use_milvus=True)
    return indexer.search(query, repo=repo, lang=lang, top_k=top_k)


def build_context(
    query: str,
    repo: Optional[str] = None,
    lang: Optional[str] = None,
    top_k: int = 5,
    include_body: bool = False,
) -> str:
    """
    Build a compact LLM-ready context string from search results.

    Args:
        query: Natural language query
        repo: Optional repo filter
        lang: Optional language filter
        top_k: Number of chunks to include
        include_body: Include full function body (longer but more complete)

    Returns:
        Markdown-formatted context string
    """
    results = search_code(query, repo=repo, lang=lang, top_k=top_k)

    if not results:
        return "No matching code found."

    lines = [f"## Relevant code (query: \"{query}\")", ""]

    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. [{r['name']}]({r['file']}#L{r['line_no']})")
        lines.append(f"**Type:** {r['chunk_type']} | **Repo:** {r['repo']} | **Score:** {r['score']:.3f}")
        lines.append(f"```\n{r['signature']}\n```")
        if r.get('docstring') and include_body:
            lines.append(f"_Doc:_ {r['docstring']}")
        if include_body and r.get('body'):
            lines.append(f"```python\n{r['body'][:300]}...\n```")
        lines.append("")

    return "\n".join(lines)


def index_repo(
    repo_path: Path,
    repo_name: Optional[str] = None,
) -> int:
    """
    Index a repository for semantic search.

    Args:
        repo_path: Path to cloned repo on disk
        repo_name: Optional "owner/repo" name

    Returns:
        Number of chunks indexed
    """
    indexer = RepoIndexer(use_milvus=True)
    return indexer.index_repo(repo_path, repo_name)


def index_all_cached(cache_dir: Path = Path("data/cache"), dry_run: bool = False) -> Dict[str, int]:
    """
    Index all repos in the RepoTransmute cache.

    Args:
        cache_dir: Path to data/cache
        dry_run: If True, only show what would be indexed

    Returns:
        Dict mapping repo names to chunk counts
    """
    indexer = RepoIndexer(use_milvus=True)
    results = {}

    for repo_path in sorted(cache_dir.iterdir()):
        if not repo_path.is_dir():
            continue
        repo_name = repo_path.name.replace("__", "/")
        if dry_run:
            chunks = indexer.extract_chunks(repo_path, repo_name)
            results[repo_name] = len(chunks)
            print(f"  Would index: {repo_name} ({len(chunks)} chunks)")
        else:
            n = indexer.index_repo(repo_path, repo_name)
            results[repo_name] = n
            print(f"  Indexed: {repo_name} ({n} chunks)")

    return results
