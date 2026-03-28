"""Semantic search interface for indexed RepoTransmute blueprints.

Provides a high-level search API on top of the txtai index, including
cross-repo pattern discovery.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from repo_transmute.txtai.client import TxtaiClient


# --------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------

@dataclass
class SearchHit:
    """A single search result."""
    uid: str
    repo: str
    language: str
    kind: str        # "function" | "class"
    name: str
    signature: str
    file: str
    line: int
    docstring: str
    score: float

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SearchHit":
        return cls(
            uid=d.get("id", ""),
            repo=d.get("repo", ""),
            language=d.get("language", ""),
            kind=d.get("kind", ""),
            name=d.get("name", ""),
            signature=d.get("signature", ""),
            file=d.get("file", ""),
            line=int(d.get("line", 0)),
            docstring=d.get("docstring", ""),
            score=d.get("score", 0.0),
        )


@dataclass
class SearchResults:
    """A collection of search hits with query metadata."""
    query: str
    hits: List[SearchHit]
    total_indexed: int

    def __len__(self) -> int:
        return len(self.hits)

    def by_repo(self, repo: str) -> "SearchResults":
        """Filter hits to a specific repo."""
        return SearchResults(
            query=self.query,
            hits=[h for h in self.hits if h.repo == repo],
            total_indexed=self.total_indexed,
        )

    def by_kind(self, kind: str) -> "SearchResults":
        """Filter hits to 'function' or 'class'."""
        return SearchResults(
            query=self.query,
            hits=[h for h in self.hits if h.kind == kind],
            total_indexed=self.total_indexed,
        )

    def functions_only(self) -> "SearchResults":
        return self.by_kind("function")

    def classes_only(self) -> "SearchResults":
        return self.by_kind("class")


# --------------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------------

class BlueprintSearch:
    """High-level semantic search over indexed blueprints.

    Example::

        search = BlueprintSearch(client)

        # Basic search
        results = search.search("authentication middleware")
        for hit in results.hits:
            print(f"[{hit.repo}] {hit.name}: {hit.signature}")

        # Filter to functions in Python repos only
        py_funcs = (
            results
            .functions_only()
        )

        # Cross-repo: find all repos that have a similar pattern
        auth_repos = {h.repo for h in results.hits}
        print(f"Repos with auth patterns: {auth_repos}")

        # Explain a result (why did this match?)
        explanation = search.explain(results.hits[0].uid)
    """

    def __init__(self, client: TxtaiClient) -> None:
        self.client = client

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> SearchResults:
        """Run a semantic search over indexed blueprints.

        Args:
            query: Natural-language query.
            limit: Maximum hits to return (default 10).

        Returns:
            SearchResults with a list of SearchHit objects.
        """
        raw = self.client.search(query, limit=limit)
        hits = [SearchHit.from_dict(r) for r in raw]
        return SearchResults(
            query=query,
            hits=hits,
            total_indexed=self.client.count(),
        )

    def search_by_repo(
        self,
        query: str,
        repo: str,
        *,
        limit: int = 10,
    ) -> SearchResults:
        """Search within a specific repo's indexed code."""
        all_results = self.client.search(query, limit=limit)
        hits = [
            SearchHit.from_dict(r)
            for r in all_results
            if r.get("repo", "") == repo
        ]
        return SearchResults(query=query, hits=hits, total_indexed=self.client.count())

    def find_similar_functions(
        self,
        function_signature: str,
        *,
        limit: int = 5,
    ) -> SearchResults:
        """Find functions with similar signatures across the index."""
        return self.search(f"function {function_signature}", limit=limit)

    def find_class_methods(
        self,
        class_name: str,
        *,
        repo: Optional[str] = None,
        limit: int = 10,
    ) -> SearchResults:
        """Find all indexed methods for a given class name."""
        query = f"class {class_name}"
        results = self.search(query, limit=limit)
        if repo:
            results = results.by_repo(repo)
        return results

    def cross_repo_patterns(
        self,
        pattern: str,
        *,
        limit_per_repo: int = 3,
    ) -> Dict[str, List[SearchHit]]:
        """Discover how ``pattern`` manifests across multiple repos.

        Returns a dict mapping repo name -> list of up to limit_per_repo hits.

        Use this to answer questions like:
          "How do different repos handle rate limiting?"
          "What caching strategies are used across our indexed code?"
        """
        all_results = self.client.search(pattern, limit=limit_per_repo * 10)
        by_repo: Dict[str, List[SearchHit]] = {}
        for r in all_results:
            hit = SearchHit.from_dict(r)
            by_repo.setdefault(hit.repo, []).append(hit)
        # Trim to limit_per_repo per repo
        return {repo: hits[:limit_per_repo] for repo, hits in by_repo.items()}

    def explain(self, uid: str) -> Dict[str, Any]:
        """Return the full indexed document for a uid (for debugging/audit)."""
        # txtai's explain is available on the embeddings directly
        return self.client.embeddings.explain(uid)  # type: ignore[return-value]

    def repos(self) -> List[str]:
        """List all unique repo names currently indexed."""
        # We do a broad search and extract unique repos from results.
        # Since txtai stores arbitrary metadata we can pull it from the index.
        count = self.client.count()
        if count == 0:
            return []
        # Search with a generic query to get a broad set of results
        raw = self.client.search("*", limit=min(count, 1000))
        return list({r.get("repo", "") for r in raw if r.get("repo")})

    def languages(self) -> List[str]:
        """List all source languages currently indexed."""
        count = self.client.count()
        if count == 0:
            return []
        raw = self.client.search("*", limit=min(count, 1000))
        return list({r.get("language", "") for r in raw if r.get("language")})
