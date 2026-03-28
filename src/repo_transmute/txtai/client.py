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
    ) -> None:
        """
        Args:
            index_dir: Directory for index + SQLite sidecar. Created if needed.
            model: HuggingFace sentence-transformers model name.
        """
        self.index_dir = Path(index_dir) if index_dir else Path("./data/txtai")
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.model = model or self.DEFAULT_MODEL

        self._config: Dict[str, Any] = {
            "path": self.model,
            "index-dir": str(self.index_dir),
        }

        self._embeddings: Optional[Embeddings] = None
        self._meta_db: Optional[Path] = None

    # ------------------------------------------------------------------
    # Internal: metadata DB
    # ------------------------------------------------------------------

    @property
    def _meta_path(self) -> Path:
        return self.index_dir / self._META_DB

    def _init_meta_db(self) -> None:
        """Create the metadata table if it doesn't exist."""
        db = self._meta_path
        conn = sqlite3.connect(db)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meta (
                uid TEXT PRIMARY KEY,
                data TEXT NOT NULL
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

        The ``text_field`` value is vectorised. All other fields are stored
        in a SQLite sidecar and retrieved after search.

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

            # Everything except the text goes into metadata
            meta = {k: v for k, v in doc.items() if k not in (text_field, uid_field)}
            self._upsert_meta(uid, meta)
            rows.append((uid, text))

        if rows:
            self.embeddings.upsert(rows)

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
