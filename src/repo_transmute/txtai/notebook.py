"""Notebook storage — treat transpiled outputs as versioned, queryable notebooks.

Each "notebook entry" captures:
  - the source blueprint that generated it
  - the raw transpiled code
  - the LLM prompt + parameters used
  - the resulting code at each refinement pass

This allows replay, diff, and audit of every transpilation.
"""

import difflib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------------
# Data models
# --------------------------------------------------------------------------------

@dataclass
class PassRecord:
    """A single LLM pass during transpilation."""
    pass_number: int
    prompt: str
    model: str
    raw_output: str
    errors_detected: List[str] = field(default_factory=list)
    refined_output: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pass_number": self.pass_number,
            "prompt": self.prompt,
            "model": self.model,
            "raw_output": self.raw_output,
            "errors_detected": self.errors_detected,
            "refined_output": self.refined_output,
        }


@dataclass
class NotebookEntry:
    """One "notebook page" = one transpilation of a chunk/repo.

    Analogous to a Jupyter notebook cell — immutable, versioned, replayable.
    """
    uid: str                    # e.g. "HKUDS/nanobot:chunk0:2026-03-28T02:00:00Z"
    repo: str                   # e.g. "HKUDS/nanobot"
    chunk_id: int               # 0-based chunk number (-1 for non-chunked)
    language: str               # source language
    target_lang: str            # e.g. "typescript"
    blueprint_text: str         # YAML blueprint (first few KB)
    passes: List[PassRecord]    # all LLM passes in order
    final_code: str             # the last pass's output (or refined)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    tags: List[str] = field(default_factory=list)   # e.g. ["auth", "api"]
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "repo": self.repo,
            "chunk_id": self.chunk_id,
            "language": self.language,
            "target_lang": self.target_lang,
            "blueprint_text": self.blueprint_text,
            "passes": [p.to_dict() for p in self.passes],
            "final_code": self.final_code,
            "created_at": self.created_at,
            "tags": self.tags,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "NotebookEntry":
        d = dict(d)
        d["passes"] = [PassRecord(**p) for p in d.get("passes", [])]
        return cls(**d)


# --------------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------------

class NotebookStore:
    """Persist notebook entries as line-delimited JSON files.

    Storage layout::

        store_dir/
          entries/
            HKUDS__nanobot.jsonl     ← one JSONL per repo
          index/
            by_repo.json
            by_tag.json
            by_language.json

    Each repo gets one ``.jsonl`` file.  The index files map
    repo → list of entry UIDs for fast lookup.
    """

    def __init__(self, store_dir: Path) -> None:
        self.store_dir = Path(store_dir)
        self.entries_dir = self.store_dir / "entries"
        self.index_dir = self.store_dir / "index"
        self.entries_dir.mkdir(parents=True, exist_ok=True)
        self.index_dir.mkdir(parents=True, exist_ok=True)

    # ---- Persistence ----

    def _repo_file(self, repo: str) -> Path:
        safe = repo.replace("/", "__")
        return self.entries_dir / f"{safe}.jsonl"

    def _load_repo_index(self, repo: str) -> List[str]:
        """Return list of UIDs in this repo's JSONL (in order)."""
        path = self._repo_file(repo)
        if not path.exists():
            return []
        uids: List[str] = []
        with path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    uids.append(d.get("uid", ""))
                except json.JSONDecodeError:
                    continue
        return uids

    def save(self, entry: NotebookEntry) -> None:
        """Append ``entry`` to the repo's JSONL file and update indexes."""
        path = self._repo_file(entry.repo)
        with path.open("a") as fh:
            fh.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

        self._update_indexes(entry)

    def _update_indexes(self, entry: NotebookEntry) -> None:
        """Keep lightweight in-memory indexes on disk."""

        def load_index(name: str) -> Dict[str, List[str]]:
            p = self.index_dir / f"{name}.json"
            if p.exists():
                with p.open() as f:
                    return json.load(f)
            return {}

        def save_index(name: str, data: Dict[str, List[str]]) -> None:
            p = self.index_dir / f"{name}.json"
            with p.open("w") as f:
                json.dump(data, f)

        # by_repo
        idx = load_index("by_repo")
        idx.setdefault(entry.repo, [])
        if entry.uid not in idx[entry.repo]:
            idx[entry.repo].append(entry.uid)
        save_index("by_repo", idx)

        # by_tag
        idx = load_index("by_tag")
        for tag in entry.tags:
            idx.setdefault(tag, [])
            if entry.uid not in idx[tag]:
                idx[tag].append(entry.uid)
        save_index("by_tag", idx)

        # by_language
        idx = load_index("by_language")
        idx.setdefault(entry.language, [])
        if entry.uid not in idx[entry.language]:
            idx[entry.language].append(entry.uid)
        save_index("by_language", idx)

    # ---- Retrieval ----

    def get(self, uid: str, repo: Optional[str] = None) -> Optional[NotebookEntry]:
        """Fetch a single entry by uid."""
        if repo:
            path = self._repo_file(repo)
        else:
            # Search all repo files — inefficient but works when repo is unknown
            for p in self.entries_dir.glob("*.jsonl"):
                path = p
                break
            else:
                return None

        if not path.exists():
            return None
        with path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    if d.get("uid") == uid:
                        return NotebookEntry.from_dict(d)
                except (json.JSONDecodeError, TypeError):
                    continue
        return None

    def list_by_repo(
        self,
        repo: str,
        *,
        limit: Optional[int] = None,
    ) -> List[NotebookEntry]:
        """Return all entries for a repo, newest first."""
        path = self._repo_file(repo)
        if not path.exists():
            return []
        entries: List[NotebookEntry] = []
        with path.open() as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(NotebookEntry.from_dict(json.loads(line)))
                except (json.JSONDecodeError, TypeError, KeyError):
                    continue
        if limit:
            entries = entries[-limit:]
        return entries

    def list_by_chunk_id(
        self,
        repo: str,
        chunk_id: int,
    ) -> List[NotebookEntry]:
        """Return all entries for a given repo and chunk_id, oldest first.

        Use this to compare successive transpilation runs for the same chunk.
        """
        entries = self.list_by_repo(repo)
        return [e for e in entries if e.chunk_id == chunk_id]

    def diff_entries(
        self,
        older: NotebookEntry,
        newer: NotebookEntry,
        *,
        context_lines: int = 3,
    ) -> str:
        """Return a unified diff between two notebook entries.

        Compares final_code from both entries.  If the two entries have
        a different number of passes, the pass counts are also noted.
        """
        if older.uid == newer.uid:
            return "(same entry — no diff)"

        older_lines = older.final_code.splitlines()
        newer_lines = newer.final_code.splitlines()

        diff_lines = difflib.unified_diff(
            older_lines,
            newer_lines,
            fromfile=f"old: {older.uid}",
            tofile=f"new: {newer.uid}",
            n=context_lines,
        )
        diff_text = "\n".join(diff_lines)

        # Include pass-count note if it differs
        notes: List[str] = []
        if len(older.passes) != len(newer.passes):
            notes.append(
                f"  Pass count: {len(older.passes)} → {len(newer.passes)}"
            )
        old_model = older.passes[0].model if older.passes else ""
        new_model = newer.passes[0].model if newer.passes else ""
        if old_model != new_model:
            notes.append(f"  Model: {old_model} → {new_model}")

        if not diff_text and notes:
            return "\n".join(notes) + "\n  (no code changes)"
        elif not diff_text:
            return "(no code changes)"
        elif notes:
            return "\n".join(notes) + "\n" + diff_text
        else:
            return diff_text

    def list_by_tag(
        self,
        tag: str,
        *,
        limit: Optional[int] = None,
    ) -> List[NotebookEntry]:
        """Return all entries with a given tag."""
        idx_path = self.index_dir / "by_tag.json"
        if not idx_path.exists():
            return []
        with idx_path.open() as f:
            idx: Dict[str, List[str]] = json.load(f)
        uids = idx.get(tag, [])
        if limit:
            uids = uids[-limit:]
        # Resolve uids to entries
        results: List[NotebookEntry] = []
        for uid in uids:
            # Determine repo from uid prefix
            repo = uid.split(":")[0]
            entry = self.get(uid, repo)
            if entry:
                results.append(entry)
        return results

    def repos(self) -> List[str]:
        """List all repos with entries in the store."""
        return [p.stem.replace("__", "/") for p in self.entries_dir.glob("*.jsonl")]

    # ---- Convenience constructors ----

    @classmethod
    def from_transpilation(
        cls,
        store_dir: Path,
        repo: str,
        chunk_id: int,
        language: str,
        target_lang: str,
        blueprint_text: str,
        passes: List[PassRecord],
        final_code: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> NotebookEntry:
        """Create and save a notebook entry from a completed transpilation run.

        This is the main entry point for capturing transpilation history.
        """
        repo_file_part = repo.replace("/", "__")
        timestamp = datetime.now(timezone.utc).isoformat()
        uid = f"{repo}:chunk{chunk_id}:{timestamp}"
        entry = NotebookEntry(
            uid=uid,
            repo=repo,
            chunk_id=chunk_id,
            language=language,
            target_lang=target_lang,
            blueprint_text=blueprint_text,
            passes=passes,
            final_code=final_code,
            tags=tags or [],
            metadata=metadata or {},
        )
        store = cls(store_dir)
        store.save(entry)
        return entry
