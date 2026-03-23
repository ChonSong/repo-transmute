"""
Repo Reaper — semantic code indexing with Milvus + SQLite fallback.
Indexes function signatures, docstrings, and bodies from any repo for
LLM context retrieval (no API required — runs locally on CPU).
"""
from __future__ import annotations

import os
import json
import hashlib
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Iterator, Dict, Any

import yaml

from repo_transmute.blueprint import Blueprint
from repo_transmute.blueprint.extractor import extract_all
from repo_transmute.ingestion.detector import detect_language
from repo_transmute.ingestion.walker import walk_source_files
from repo_transmute.transpiler.chunker import chunk_repository, Chunk

from repo_reaper.embedder import get_embedder, encode_texts


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class CodeChunk:
    """A unit of code ready for embedding + storage."""
    chunk_id: str          # SHA of file+name+line
    repo: str              # "owner/repo"
    lang: str              # "python", "typescript", etc.
    file: str              # relative file path
    chunk_type: str        # "function", "class", "method"
    name: str              # function/class name
    signature: str         # full signature line
    docstring: str         # first docstring or ""
    body: str              # full function/class body
    line_no: int           # line number in source

    def to_text(self) -> str:
        """Concise text for embedding — focuses on name + signature + doc."""
        parts = [f"{self.chunk_type} {self.name}", f"sig: {self.signature}"]
        if self.docstring:
            parts.append(f"doc: {self.docstring.split(chr(10))[0]}")
        return " | ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def make_id(repo: str, file: str, name: str, line_no: int) -> str:
        raw = f"{repo}:{file}:{name}:{line_no}"
        return hashlib.sha1(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Milvus collection management
# ---------------------------------------------------------------------------

MILVUS_URI = os.environ.get("MILVUS_URI", "http://localhost:19530")
COLLECTION_NAME = "repo_reaper"
EMBED_DIM = 384  # matches BAAI/bge-small-en-v1.5 and all-MiniLM-L6-v2

# Milvus schema fields
FIELDS = [
    {"name": "chunk_id", "type": "varchar", "params": {"max_length": 32}, "auto_id": False},
    {"name": "repo",     "type": "varchar", "params": {"max_length": 128}},
    {"name": "lang",     "type": "varchar", "params": {"max_length": 32}},
    {"name": "file",     "type": "varchar", "params": {"max_length": 512}},
    {"name": "chunk_type", "type": "varchar", "params": {"max_length": 32}},
    {"name": "name",     "type": "varchar", "params": {"max_length": 256}},
    {"name": "signature", "type": "varchar", "params": {"max_length": 1024}},
    {"name": "docstring", "type": "varchar", "params": {"max_length": 2048}},
    {"name": "line_no",  "type": "int64"},
    {"name": "embedding", "type": "float_vector", "params": {"dim": EMBED_DIM}},
]


# ---------------------------------------------------------------------------
# Milvus client (lazy)
# ---------------------------------------------------------------------------

_milvus_client = None


def get_milvus_client():
    global _milvus_client
    if _milvus_client is None:
        from pymilvus import MilvusClient
        _milvus_client = MilvusClient(uri=MILVUS_URI)
    return _milvus_client


def ensure_collection(exists_ok: bool = True) -> bool:
    """
    Create the Milvus collection if it doesn't exist.
    Returns True if collection is ready (exists or created).
    """
    client = get_milvus_client()
    if COLLECTION_NAME in client.list_collections():
        return True

    try:
        from pymilvus import DataType

        schema = client.create_schema(auto_id=False)
        schema.add_field("chunk_id",  DataType.VARCHAR, max_length=32,   is_primary=True)
        schema.add_field("repo",      DataType.VARCHAR, max_length=128)
        schema.add_field("lang",      DataType.VARCHAR, max_length=32)
        schema.add_field("file",      DataType.VARCHAR, max_length=512)
        schema.add_field("chunk_type", DataType.VARCHAR, max_length=32)
        schema.add_field("name",      DataType.VARCHAR, max_length=256)
        schema.add_field("signature", DataType.VARCHAR, max_length=1024)
        schema.add_field("docstring", DataType.VARCHAR, max_length=2048)
        schema.add_field("line_no",   DataType.INT64)
        schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=EMBED_DIM)

        client.create_collection(collection_name=COLLECTION_NAME, schema=schema)

        # HNSW index for fast ANN search
        index_params = client.prepare_index_params()
        index_params.add_index(
            field_name="embedding",
            index_type="HNSW",
            metric_type="COSINE",
            params={"M": 16, "efConstruction": 128},
        )
        client.create_index(collection_name=COLLECTION_NAME, index_params=index_params)
        client.load_collection(COLLECTION_NAME)
        print(f"✅ Milvus collection '{COLLECTION_NAME}' created (dim={EMBED_DIM})")
        return True
    except Exception as e:
        print(f"❌ Milvus collection creation failed: {e}")
        return False


# ---------------------------------------------------------------------------
# SQLite fallback store
# ---------------------------------------------------------------------------

FALLBACK_DB = Path("~/.openclaw/memory/fallback_memories.db").expanduser()


def _init_fallback_db():
    FALLBACK_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(FALLBACK_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS repo_chunks (
            chunk_id   TEXT PRIMARY KEY,
            repo       TEXT,
            lang       TEXT,
            file       TEXT,
            chunk_type TEXT,
            name       TEXT,
            signature  TEXT,
            docstring  TEXT,
            body       TEXT,
            line_no    INTEGER,
            embedding  BLOB,
            indexed_at INTEGER
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_repo ON repo_chunks(repo)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_name ON repo_chunks(name)")
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Core indexer
# ---------------------------------------------------------------------------

class RepoIndexer:
    """
    Indexes code from a repository into Milvus (or SQLite fallback).

    Usage:
        indexer = RepoIndexer()
        indexer.index_repo(Path("data/cache/HKUDS__nanobot"), repo="HKUDS/nanobot")
        results = indexer.search("agent loop implementation")
    """

    def __init__(
        self,
        use_milvus: bool = True,
        batch_size: int = 64,
        cache_dir: Optional[Path] = None,
    ):
        self.batch_size = batch_size
        self.cache_dir = cache_dir or Path("~/.openclaw/cache/repo_reaper")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._milvus_ok = False
        self._fallback_ok = False

        _init_fallback_db()

        if use_milvus:
            try:
                ensure_collection()
                self._milvus_ok = True
                print("✅ Milvus mode active")
            except Exception as e:
                print(f"⚠️  Milvus unavailable ({e}), using SQLite fallback")

        if not self._milvus_ok:
            self._fallback_ok = True
            print("✅ SQLite fallback mode active")

    # ── Extraction ─────────────────────────────────────────────────────────

    @staticmethod
    def extract_chunks(repo_path: Path, repo_name: str) -> List[CodeChunk]:
        """Extract all code chunks from a repo."""
        lang = detect_language(repo_path)
        files = list(walk_source_files(repo_path))

        chunks = []

        if lang == "python":
            from repo_transmute.blueprint.extractor import extract_from_python, extract_classes_from_python
            for fp in files:
                try:
                    funcs = extract_from_python(fp)
                    for f in funcs:
                        chunks.append(CodeChunk(
                            chunk_id=CodeChunk.make_id(repo_name, str(fp.relative_to(repo_path)), f.name, f.line),
                            repo=repo_name,
                            lang=lang,
                            file=str(fp.relative_to(repo_path)),
                            chunk_type="function",
                            name=f.name,
                            signature=f.signature or f.name,
                            docstring=getattr(f, "body", "")[:200] if hasattr(f, "body") else "",
                            body=getattr(f, "body", "") if hasattr(f, "body") else "",
                            line_no=f.line,
                        ))
                    # Also extract classes
                    for cls in extract_classes_from_python(fp):
                        chunks.append(CodeChunk(
                            chunk_id=CodeChunk.make_id(repo_name, str(fp.relative_to(repo_path)), cls.name, cls.line),
                            repo=repo_name,
                            lang=lang,
                            file=str(fp.relative_to(repo_path)),
                            chunk_type="class",
                            name=cls.name,
                            signature=f"class {cls.name}",
                            docstring="",
                            body="",
                            line_no=cls.line,
                        ))
                except Exception:
                    continue

        elif lang in ("javascript", "typescript"):
            from repo_transmute.blueprint.extractor import extract_from_typescript, extract_from_javascript
            extractor = extract_from_typescript if lang == "typescript" else extract_from_javascript
            for fp in files:
                try:
                    for f in extractor(fp):
                        chunks.append(CodeChunk(
                            chunk_id=CodeChunk.make_id(repo_name, str(fp.relative_to(repo_path)), f.name, f.line),
                            repo=repo_name,
                            lang=lang,
                            file=str(fp.relative_to(repo_path)),
                            chunk_type="function",
                            name=f.name,
                            signature=f.signature or f.name,
                            docstring="",
                            body="",
                            line_no=f.line,
                        ))
                except Exception:
                    continue

        return chunks

    # ── Indexing ──────────────────────────────────────────────────────────

    def index_repo(self, repo_path: Path, repo_name: Optional[str] = None) -> int:
        """
        Index all code from a repository.

        Args:
            repo_path: Path to cloned repo on disk
            repo_name: "owner/repo" name (inferred from path if not given)

        Returns:
            Number of chunks indexed
        """
        if repo_name is None:
            # Infer from path like "data/cache/HKUDS__nanobot"
            repo_name = repo_path.name.replace("__", "/")

        print(f"Indexing {repo_name} from {repo_path}...")

        # Check cache
        cache_file = self.cache_dir / f"{hashlib.sha1(repo_name.encode()).hexdigest()[:8]}.json"
        if cache_file.exists():
            chunks = [
                CodeChunk(**c)
                for c in json.loads(cache_file.read_text())
            ]
            print(f"  Loaded {len(chunks)} chunks from cache")
        else:
            chunks = self.extract_chunks(repo_path, repo_name)
            cache_file.write_text(json.dumps([c.to_dict() for c in chunks]))
            print(f"  Extracted {len(chunks)} chunks")

        if not chunks:
            print("  Nothing to index")
            return 0

        # Embed in batches
        texts = [c.to_text() for c in chunks]
        embedder = get_embedder()
        embeddings = embedder.encode(texts, normalize=True)

        if self._milvus_ok:
            return self._index_milvus(chunks, embeddings)
        else:
            return self._index_fallback(chunks, embeddings)

    def _index_milvus(self, chunks: List[CodeChunk], embeddings) -> int:
        client = get_milvus_client()

        # Delete existing chunks for this repo first (upsert-style)
        try:
            client.delete(
                collection_name=COLLECTION_NAME,
                filter=f'repo == "{chunks[0].repo}"',
            )
        except Exception:
            pass

        records = []
        for chunk, emb in zip(chunks, embeddings):
            records.append({
                "chunk_id":  chunk.chunk_id,
                "repo":      chunk.repo,
                "lang":      chunk.lang,
                "file":      chunk.file,
                "chunk_type": chunk.chunk_type,
                "name":      chunk.name,
                "signature": chunk.signature,
                "docstring": chunk.docstring,
                "line_no":   chunk.line_no,
                "embedding": emb,
            })

        client.insert(collection_name=COLLECTION_NAME, data=records)
        print(f"  ✅ Milvus: indexed {len(records)} chunks")
        return len(records)

    def _index_fallback(self, chunks: List[CodeChunk], embeddings) -> int:
        import numpy as np
        conn = sqlite3.connect(FALLBACK_DB)
        indexed = 0
        now = int(datetime.now().timestamp())

        for chunk, emb in zip(chunks, embeddings):
            emb_bytes = np.array(emb, dtype=np.float32).tobytes()
            try:
                conn.execute("""
                    INSERT OR REPLACE INTO repo_chunks
                    (chunk_id, repo, lang, file, chunk_type, name, signature, docstring, body, line_no, embedding, indexed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    chunk.chunk_id, chunk.repo, chunk.lang, chunk.file, chunk.chunk_type,
                    chunk.name, chunk.signature, chunk.docstring, chunk.body,
                    chunk.line_no, emb_bytes, now,
                ))
                indexed += 1
            except Exception:
                pass

        conn.commit()
        conn.close()
        print(f"  ✅ SQLite fallback: indexed {indexed} chunks")
        return indexed

    # ── Search ────────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        repo: Optional[str] = None,
        lang: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Semantic search across indexed code.

        Args:
            query: Natural language query
            repo: Optional filter by repo name
            lang: Optional filter by language
            top_k: Number of results to return

        Returns:
            List of result dicts with chunk info + similarity score
        """
        embedder = get_embedder()
        q_emb = embedder.encode_one(query, normalize=True)

        if self._milvus_ok:
            return self._search_milvus(q_emb, repo=repo, lang=lang, top_k=top_k)
        else:
            return self._search_fallback(q_emb, repo=repo, lang=lang, top_k=top_k)

    def _search_milvus(
        self, q_emb, repo: Optional[str], lang: Optional[str], top_k: int
    ) -> List[Dict[str, Any]]:
        client = get_milvus_client()

        filters = []
        if repo:
            filters.append(f'repo == "{repo}"')
        if lang:
            filters.append(f'lang == "{lang}"')
        flt = " && ".join(filters) if filters else ""

        results = client.search(
            collection_name=COLLECTION_NAME,
            data=[q_emb],
            limit=top_k,
            output_fields=["chunk_id", "repo", "lang", "file", "chunk_type",
                           "name", "signature", "docstring", "line_no"],
            filter=flt or None,
        )

        out = []
        for hit in (results[0] if results else []):
            r = hit["entity"]
            r["score"] = float(hit.get("distance", 0))
            out.append(r)
        return out

    def _search_fallback(
        self, q_emb, repo: Optional[str], lang: Optional[str], top_k: int
    ) -> List[Dict[str, Any]]:
        import numpy as np

        conn = sqlite3.connect(FALLBACK_DB)
        query = "SELECT * FROM repo_chunks"
        wheres = []
        if repo:
            wheres.append(f"repo = '{repo}'")
        if lang:
            wheres.append(f"lang = '{lang}'")
        if wheres:
            query += " WHERE " + " AND ".join(wheres)

        rows = conn.execute(query).fetchall()
        cols = [d[0] for d in conn.execute(
            "SELECT name FROM pragma_table_info('repo_chunks')").fetchall()]
        conn.close()

        scored = []
        for row in rows:
            r = dict(zip(cols, row))
            emb = np.frombuffer(r.pop("embedding", b""), dtype=np.float32)
            if len(emb) != len(q_emb):
                continue
            score = float(np.dot(emb, q_emb))
            r["score"] = score
            scored.append(r)

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]

    def stats(self) -> Dict[str, int]:
        """Return index statistics."""
        if self._milvus_ok:
            client = get_milvus_client()
            try:
                coll = client.get_collection_stats(COLLECTION_NAME)
                return {"milvus": coll.get("row_count", 0), "mode": "milvus"}
            except Exception:
                pass
        conn = sqlite3.connect(FALLBACK_DB)
        n = conn.execute("SELECT COUNT(*) FROM repo_chunks").fetchone()[0]
        conn.close()
        return {"sqlite": n, "mode": "sqlite"}
