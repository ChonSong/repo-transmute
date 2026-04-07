"""TXTAI client wrapper for RepoTransmute.

Provides a configured Embeddings instance and convenience methods.
Search results include stored metadata by looking up UIDs in a
SQLite sidecar that is written alongside the faiss index.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from txtai import Embeddings


class TxtaiClient:
    """Thin wrapper around txtai Embeddings for RepoTransmute.

    Each indexed document has:
      - a vector (used for semantic search)
      - a uid (used to retrieve stored metadata from SQLite)

    The SQLite sidecar (``metadata.db``) is created in ``index_dir`` alongside
    the faiss index files, so saving/loading the txtai index automatically
    gives you the metadata too.

    Usage::

        client = TxtaiClient(index_dir=Path("./data/txtai"))
        client.index([{"id": "f1", "text": "function hello", "repo": "a/b"}])
        results = client.search("hello function")   # [{id, text, score, repo, ...}]
        client.save()
        client.close()

        # ... later:
        client = TxtaiClient(index_dir=Path("./data/txtai"))
        client.load()
        results = client.search("greeting")
    """

    # Lightweight CPU-friendly model
    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    # SQLite sidecar filename inside index_dir
    _META_DB = "metadata.db"

    def __init__(
        self,
        index_dir: Optional[Path] = None,
        model: Optional[str] = None,
        *,
        autoload: bool = True,
    ) -> None:
        """
        Args:
            index_dir: Directory for index + SQLite sidecar. Created if needed.
            model: HuggingFace sentence-transformers model name.
            autoload: If True and an index exists at index_dir, load it immediately (default).
                      Pass False to skip auto-loading (useful when building a fresh index).
        """
        self.index_dir = Path(index_dir) if index_dir else Path("./data/txtai")
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.model = model or self.DEFAULT_MODEL
        self.autoload = autoload

        self._config: Dict[str, Any] = {
            "path": self.model,
            "index-dir": str(self.index_dir),
        }

        self._embeddings: Optional[Embeddings] = None

        if self.autoload and (self.index_dir / "config.json").exists():
            self.load()

    # ------------------------------------------------------------------
    # Internal: metadata DB
    # ------------------------------------------------------------------

    @property
    def _meta_path(self) -> Path:
        return self.index_dir / self._META_DB

    def _init_meta_db(self) -> None:
        """Create the metadata tables if they don't exist."""
        db = self._meta_path
        conn = sqlite3.connect(db)
        # Per-document metadata (existing)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                uid TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
            """
        )
        # Per-repo last-indexed timestamps (Phase 7 — deduplication)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS repo_meta (
                repo TEXT PRIMARY KEY,
                last_indexed TEXT NOT NULL,
                last_modified TEXT
            )
            """
        )
        conn.commit()
        conn.close()

    def _upsert_meta(self, uid: str, data: Dict[str, Any]) -> None:
        conn = sqlite3.connect(self._meta_path)
        conn.execute(
            "INSERT OR REPLACE INTO meta (uid, data) VALUES (?, ?)",
            (uid, json.dumps(data)),
        )
        conn.commit()
        conn.close()

    def _fetch_meta(self, uids: Sequence[str]) -> Dict[str, Dict[str, Any]]:
        """Batch-fetch metadata for a list of UIDs."""
        if not uids:
            return {}
        conn = sqlite3.connect(self._meta_path)
        placeholders = ",".join("?" * len(uids))
        rows = conn.execute(
            f"SELECT uid, data FROM meta WHERE uid IN ({placeholders})",
            list(uids),
        ).fetchall()
        conn.close()
        return {uid: json.loads(data) for uid, data in rows}

    # ------------------------------------------------------------------
    # Repo-level metadata (last_indexed timestamps for deduplication)
    # ------------------------------------------------------------------

    def set_repo_last_indexed(
        self,
        repo: str,
        last_indexed: str,
        last_modified: Optional[str] = None,
    ) -> None:
        """Record when a repo was last indexed.

        Args:
            repo: Repository identifier, e.g. "HKUDS/nanobot"
            last_indexed: ISO-8601 timestamp of this indexing run
            last_modified: ISO-8601 timestamp of the last git commit
                           that contributed to this index (None = unknown)
        """
        conn = sqlite3.connect(self._meta_path)
        conn.execute(
            """
            INSERT OR REPLACE INTO repo_meta (repo, last_indexed, last_modified)
            VALUES (?, ?, ?)
            """,
            (repo, last_indexed, last_modified),
        )
        conn.commit()
        conn.close()

    def get_repo_last_indexed(self, repo: str) -> Optional[str]:
        """Return the last_indexed timestamp for a repo, or None if never indexed."""
        conn = sqlite3.connect(self._meta_path)
        row = conn.execute(
            "SELECT last_indexed FROM repo_meta WHERE repo = ?",
            (repo,),
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def get_repo_last_modified(self, repo: str) -> Optional[str]:
        """Return the last_modified (git commit time) for a repo's last indexing run."""
        conn = sqlite3.connect(self._meta_path)
        row = conn.execute(
            "SELECT last_modified FROM repo_meta WHERE repo = ?",
            (repo,),
        ).fetchone()
        conn.close()
        return row[0] if row else None

    def get_indexed_repos(self) -> List[Dict[str, str]]:
        """Return all repos that have been indexed, with their last_indexed times.

        Returns:
            List of dicts: [{"repo": "owner/repo", "last_indexed": "...", "last_modified": "..."}]
        """
        conn = sqlite3.connect(self._meta_path)
        rows = conn.execute(
            "SELECT repo, last_indexed, last_modified FROM repo_meta ORDER BY repo"
        ).fetchall()
        conn.close()
        return [
            {"repo": r[0], "last_indexed": r[1], "last_modified": r[2]}
            for r in rows
        ]

    def get_indexed_repo_names(self) -> List[str]:
        """Return just the repo names that have been indexed."""
        conn = sqlite3.connect(self._meta_path)
        rows = conn.execute(
            "SELECT repo FROM repo_meta ORDER BY repo"
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    @property
    def embeddings(self) -> Embeddings:
        """Lazily create the Embeddings instance on first access."""
        if self._embeddings is None:
            self._embeddings = Embeddings(self._config)
        return self._embeddings

    def close(self) -> None:
        if self._embeddings is not None:
            self._embeddings.close()
            self._embeddings = None

    def save(self) -> None:
        """Persist the faiss index to ``self.index_dir``."""
        self.embeddings.save(str(self.index_dir))

    def load(self) -> None:
        """Reload a previously saved index."""
        # txtai saves config.json + embeddings + ids (no index.faiss file)
        if not (self.index_dir / "config.json").exists():
            raise FileNotFoundError(
                f"No txtai index found in {self.index_dir}. "
                "Call save() or index() first."
            )
        self._embeddings = Embeddings()
        self._embeddings.load(str(self.index_dir))

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index(
        self,
        documents: Sequence[Dict[str, Any]],
        *,
        text_field: str = "text",
        uid_field: str = "id",
    ) -> None:
        """Index documents for semantic search.

        The ``text_field`` value is vectorised. All other fields, INCLUDING
        ``text_field`` itself, are stored in a SQLite sidecar and retrieved
        after search and in :meth:`get_document`.

        Args:
            documents: Dicts with at least ``text_field`` and ``uid_field``.
            text_field: Key whose value is the string to embed.
            uid_field:  Key whose value is the unique document id.
        """
        self._init_meta_db()

        rows = []
        for doc in documents:
            uid = str(doc.get(uid_field, ""))
            text = str(doc.get(text_field, ""))
            if not text or not uid:
                continue

            # Everything including text goes into metadata so get_document() can return it
            meta = {k: v for k, v in doc.items() if k != uid_field}
            self._upsert_meta(uid, meta)
            rows.append((uid, text))

        if rows:
            self.embeddings.upsert(rows)
            self.save()  # persist immediately

    def delete(self, uids: Sequence[str]) -> None:
        """Remove documents by uid (from both faiss and SQLite)."""
        self.embeddings.delete([str(u) for u in uids])
        if self._meta_path.exists():
            conn = sqlite3.connect(self._meta_path)
            placeholders = ",".join("?" * len(uids))
            conn.execute(
                f"DELETE FROM meta WHERE uid IN ({placeholders})",
                list(uids),
            )
            conn.commit()
            conn.close()

    def count(self) -> int:
        return self.embeddings.count()

    def get_document(self, uid: str) -> Optional[Dict[str, Any]]:
        """Retrieve the full stored document for a uid (metadata + text).

        Returns None if the uid is not found in the index.
        """
        meta = self._fetch_meta([uid]).get(uid)
        if meta is None:
            return None
        return {"id": uid, **meta}

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Semantic search over indexed blueprints.

        Returns enriched results: ``(uid, score)`` pairs are augmented with
        the metadata stored during :meth:`index`.

        Args:
            query: Natural-language query string.
            limit: Maximum results to return.

        Returns:
            List of dicts: ``[{uid, score, ...stored_metadata}]``
        """
        raw: List[tuple] = self.embeddings.search(query, limit=limit)

        # raw items are (uid, score) tuples when content is disabled
        uids = [item[0] for item in raw]
        meta_map = self._fetch_meta(uids)

        results = []
        for uid, score in raw:
            result: Dict[str, Any] = {
                "id": str(uid),
                "score": float(score),
            }
            result.update(meta_map.get(str(uid), {}))
            results.append(result)

        return results

    def similarity(
        self,
        texts: Sequence[str],
        query: str,
    ) -> List[float]:
        """Return cosine-similarity scores between each text and the query."""
        return self.embeddings.similarity(texts, query)  # type: ignore[return-value]