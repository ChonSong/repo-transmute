"""Semantic search interface for indexed RepoTransmute blueprints.

Provides a high-level search API on top of the txtai index, including
cross-repo pattern discovery.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from repo_transmute.txtai.client import TxtaiClient


# --------------------------------------------------------------------------------
# Result types
# --------------------------------------------------------------------------------

@dataclass
class SearchHit:
    """A single search result.

    Attributes:
        uid: Unique document ID in the index.
        repo: Repo name, e.g. "HKUDS/nanobot".
        language: Source language, e.g. "python".
        kind: "function" or "class".
        name: Function or class name.
        signature: Full function signature (empty for classes).
        file: Source file path.
        line: Line number in source.
        docstring: First 300 chars of docstring (may be empty).
        snippet: A focused code snippet from the function/class body,
                 extracted for relevance. Best-effort: falls back to
                 docstring or signature if body is not available.
        score: Relevance score from txtai (0.0–1.0, higher = more relevant).
    """
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
    snippet: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SearchHit":
        snippet = cls._extract_snippet(
            d.get("body", ""),
            d.get("docstring", ""),
            d.get("signature", ""),
        )
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
            score=float(d.get("score", 0.0)),
            snippet=snippet,
        )

    @staticmethod
    def _extract_snippet(body: str, docstring: str, signature: str) -> str:
        """Extract a focused, readable snippet from available text fields.

        Priority:
        1. Function body — first 200 chars, cleaned of excessive whitespace.
        2. Docstring if body is empty.
        3. Signature if both body and docstring are empty.
        4. Empty string as last resort.
        """
        if body:
            # Take first meaningful chunk, collapse internal newlines to spaces
            lines = body.split("\n")
            first_lines = []
            total = 0
            for l in lines:
                stripped = l.strip()
                if not stripped:
                    continue
                if total + len(stripped) > 200:
                    remaining = 200 - total
                    if remaining >= 20:
                        first_lines.append(stripped[:remaining] + " ...")
                    break
                first_lines.append(stripped)
                total += len(stripped) + 1
                if total > 200:
                    break
            return " ".join(first_lines).strip()
        if docstring:
            return docstring[:200].strip()
        if signature:
            return signature
        return ""

    def as_dict(self) -> Dict[str, Any]:
        """Serialize this hit to a plain dict (JSON-safe)."""
        return {
            "uid": self.uid,
            "repo": self.repo,
            "language": self.language,
            "kind": self.kind,
            "name": self.name,
            "signature": self.signature,
            "file": self.file,
            "line": self.line,
            "docstring": self.docstring,
            "snippet": self.snippet,
            "score": round(self.score, 4),
        }

    @property
    def location(self) -> str:
        """Short location string: 'file:line'."""
        return f"{self.file}:{self.line}"

    @property
    def repo_short(self) -> str:
        """Repo with '/' replaced by ' › ' for display: 'HKUDS › nanobot'."""
        return self.repo.replace("/", " › ", 1)

    def score_bar(self, width: int = 10) -> str:
        """Unicode bar representing score (0.0–1.0)."""
        filled = int(round(self.score * width))
        return "█" * filled + "░" * (width - filled)


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

    def by_language(self, language: str) -> "SearchResults":
        """Filter hits to a specific source language."""
        return SearchResults(
            query=self.query,
            hits=[h for h in self.hits if h.language == language],
            total_indexed=self.total_indexed,
        )

    def functions_only(self) -> "SearchResults":
        return self.by_kind("function")

    def classes_only(self) -> "SearchResults":
        return self.by_kind("class")

    def as_dicts(self) -> List[Dict[str, Any]]:
        """Serialize all hits to a list of plain dicts (JSON-safe)."""
        return [h.as_dict() for h in self.hits]

    @property
    def best(self) -> Optional[SearchHit]:
        """Top-scoring hit, or None if results are empty."""
        return self.hits[0] if self.hits else None


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
            if hit.snippet:
                print(f"  → {hit.snippet}")

        # Top result
        best = results.best
        if best:
            print(f"Best match: {best.name} (score={best.score:.3f})")

        # Filter to functions in Python repos only
        py_funcs = results.functions_only().by_language("python")

        # Cross-repo: find all repos that have a similar pattern
        auth_repos = {h.repo for h in results.hits}
        print(f"Repos with auth patterns: {auth_repos}")

        # Explain a result (why did this match?)
        explanation = search.explain(results.hits[0].uid)

        # JSON output
        import json
        print(json.dumps(results.as_dicts(), indent=2))
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
            SearchResults with a list of SearchHit objects, sorted by
            descending relevance score.
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

        Returns a dict mapping repo name -> list of up to limit_per_repo hits,
        sorted by descending score within each repo.

        Use this to answer questions like:
          "How do different repos handle rate limiting?"
          "What caching strategies are used across our indexed code?"
        """
        all_results = self.client.search(pattern, limit=limit_per_repo * 10)
        by_repo: Dict[str, List[SearchHit]] = {}
        for r in all_results:
            hit = SearchHit.from_dict(r)
            by_repo.setdefault(hit.repo, []).append(hit)
        # Sort each repo's hits by score descending, then trim
        return {
            repo: sorted(hits, key=lambda h: h.score, reverse=True)[:limit_per_repo]
            for repo, hits in by_repo.items()
        }

    def explain(self, uid: str) -> Dict[str, Any]:
        """Return the full indexed document for a uid (for debugging/audit).

        Uses the metadata sidecar to reconstruct the complete stored document
        (text + all metadata fields) rather than txtai's token-scoring explain.
        """
        doc = self.client.get_document(uid)
        if doc is None:
            return {"error": f"UID '{uid}' not found in index"}
        return doc

    def repos(self) -> List[str]:
        """List all unique repo names currently indexed."""
        count = self.client.count()
        if count == 0:
            return []
        raw = self.client.search("*", limit=min(count, 1000))
        return sorted({r.get("repo", "") for r in raw if r.get("repo")})

    def languages(self) -> List[str]:
        """List all source languages currently indexed."""
        count = self.client.count()
        if count == 0:
            return []
        raw = self.client.search("*", limit=min(count, 1000))
        return sorted({r.get("language", "") for r in raw if r.get("language")})

    def stats(self) -> Dict[str, int]:
        """Return summary statistics for the current index."""
        count = self.client.count()
        if count == 0:
            return {"total": 0, "repos": 0, "languages": 0}
        raw = self.client.search("*", limit=min(count, 1000))
        repos = {r.get("repo", "") for r in raw if r.get("repo")}
        langs = {r.get("language", "") for r in raw if r.get("language")}
        return {
            "total": count,
            "repos": len(repos),
            "languages": len(langs),
        }
