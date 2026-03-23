"""
Repo Reaper CLI — semantic code search and indexing for repos.

Usage:
    repo-reaper index <repo-path> [--repo-name owner/repo]
    repo-reaper search <query> [--repo owner/repo] [--lang python] [--top-k 5]
    repo-reaper stats
    repo-reaper context <query> [--repo owner/repo] [--top-k 5] [--include-body]
"""
from __future__ import annotations

import sys
from pathlib import Path

import click

# Add repo-transmute src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "repo-transmute" / "src"))

from repo_reaper.indexer import RepoIndexer, COLLECTION_NAME
from repo_reaper.rag import search_code, build_context, index_all_cached


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Repo Reaper — semantic code search for indexed repositories."""
    pass


@cli.command()
@click.argument("repo_path", type=click.Path(exists=True, path_type=Path))
@click.option("--repo-name", "-n", default=None, help="Repo name (e.g. HKUDS/nanobot). Inferred from path if not given.")
@click.option("--cache-dir", "-c", default=None, help="Override cache dir for caching extracted chunks")
def index(repo_path: Path, repo_name: str | None, cache_dir: str | None):
    """Index a repository for semantic search."""
    indexer = RepoIndexer(use_milvus=True, cache_dir=Path(cache_dir) if cache_dir else None)
    n = indexer.index_repo(repo_path, repo_name)
    stats = indexer.stats()
    click.echo(f"✅ Indexed {n} chunks. Total in index: {stats}")


@cli.command()
@click.argument("query")
@click.option("--repo", "-r", default=None, help="Filter by repo name")
@click.option("--lang", "-l", default=None, help="Filter by language (python, typescript)")
@click.option("--top-k", "-k", default=5, help="Number of results")
def search(query: str, repo: str | None, lang: str | None, top_k: int):
    """Semantic search across indexed repositories."""
    results = search_code(query, repo=repo, lang=lang, top_k=top_k)
    if not results:
        click.echo("No results found.")
        return

    for i, r in enumerate(results, 1):
        score = r.get("score", 0)
        name = r.get("name", "?")
        file = r.get("file", "?")
        chunk_type = r.get("chunk_type", "?")
        sig = r.get("signature", "")
        click.echo(f"\n{i}. [{score:.3f}] {name} ({chunk_type})")
        click.echo(f"   File: {file}")
        if sig:
            click.echo(f"   Sig:  {sig}")


@cli.command()
@click.argument("query")
@click.option("--repo", "-r", default=None)
@click.option("--lang", "-l", default=None)
@click.option("--top-k", "-k", default=5)
@click.option("--include-body/--no-body", default=False, help="Include full function bodies")
def context(query: str, repo: str | None, lang: str | None, top_k: int, include_body: bool):
    """Build LLM-ready context from semantic search results."""
    ctx = build_context(query, repo=repo, lang=lang, top_k=top_k, include_body=include_body)
    click.echo(ctx)


@cli.command()
def stats():
    """Show index statistics."""
    indexer = RepoIndexer(use_milvus=True)
    s = indexer.stats()
    click.echo(f"Mode:  {s.get('mode', 'unknown')}")
    click.echo(f"Total chunks: {s.get('milvus', s.get('sqlite', 'N/A'))}")


@cli.command()
@click.argument("cache_dir", type=click.Path(exists=True, path_type=Path), default=Path("data/cache"))
@click.option("--dry-run", is_flag=True, help="Show what would be indexed without indexing")
def index_all(cache_dir: Path, dry_run: bool):
    """Index all repos in the RepoTransmute cache directory."""
    results = index_all_cached(cache_dir, dry_run=dry_run)
    total = sum(results.values())
    click.echo(f"\nIndexed {len(results)} repos, {total} total chunks")


if __name__ == "__main__":
    cli()
