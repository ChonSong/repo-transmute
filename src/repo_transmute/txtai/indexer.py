"""Blueprint indexer — convert RepoTransmute blueprints into indexable txtai documents."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import yaml

from repo_transmute.blueprint import Blueprint
from repo_transmute.blueprint.extractor import DataStructure, Function
from repo_transmute.txtai.client import TxtaiClient


# --------------------------------------------------------------------------------
# Document schema
# --------------------------------------------------------------------------------

#: Fields stored on every indexed document
INDEX_SCHEMA = {
    "id": "uid",          # "owner__repo:func:lineno" or "owner__repo:ds:lineno"
    "text": "text",       # the embedded free-text string
    "repo": "repo",       # e.g. "HKUDS/nanobot"
    "language": "language",  # e.g. "python"
    "kind": "kind",       # "function" | "class" | "module"
    "name": "name",       # function or class name
    "signature": "signature",  # for functions
    "file": "file",       # source file path
    "line": "line",       # line number in source
    "docstring": "docstring",  # first 200 chars
    "decorators": "decorators",  # list[str]
    "chunk_id": "chunk_id",  # int — which chunk this came from
}


# --------------------------------------------------------------------------------
# Converters
# --------------------------------------------------------------------------------

def _truncate(text: Optional[str], length: int = 300) -> str:
    """Return text truncated to ``length`` chars, or '' if None."""
    if not text:
        return ""
    return text[:length].strip()


def _build_text(func: Function) -> str:
    """Build the embedded text for a function document."""
    parts = [
        f"function {func.name}",
        f"signature: {func.signature}",
        f"file: {func.file}:{func.line}",
    ]
    if func.docstring:
        parts.append(f"doc: {func.docstring}")
    if func.decorators:
        parts.append(f"decorators: {', '.join(func.decorators)}")
    if func.body:
        parts.append(f"body: {func.body[:500]}")
    return " | ".join(parts)


def _build_text_for_ds(ds: DataStructure) -> str:
    """Build the embedded text for a class/struct document."""
    method_sigs = ", ".join(m.signature for m in ds.methods) if ds.methods else ""
    parts = [
        f"class {ds.name}",
        f"type: {ds.type}",
        f"file: {ds.file}:{ds.line}",
        f"bases: {', '.join(ds.fields)}",
    ]
    if ds.docstring:
        parts.append(f"doc: {ds.docstring}")
    if method_sigs:
        parts.append(f"methods: {method_sigs}")
    return " | ".join(parts)


def _function_uid(repo: str, func: Function, chunk_id: int) -> str:
    return f"{repo}:func:{func.file}:{func.line}:chunk{chunk_id}"


def _ds_uid(repo: str, ds: DataStructure, chunk_id: int) -> str:
    return f"{repo}:class:{ds.file}:{ds.line}:chunk{chunk_id}"


# --------------------------------------------------------------------------------
# Chunk-file loader (legacy format)
# --------------------------------------------------------------------------------

def _load_chunk_file(yaml_path: Path) -> Optional[Dict[str, Any]]:
    """Load a legacy chunk file and return its data, or None if not a chunk file.

    Legacy chunk files have the format:
        {chunk: N, files: [...], total_chunks: M}

    Modern full blueprints have:
        {version, generated, source: {repo, language}, blueprint: {functions, data_structures}}
    """
    with open(yaml_path) as f:
        data = yaml.safe_load(f)
    # Must have 'source' and 'blueprint' to be a modern full blueprint
    if "source" in data and "blueprint" in data:
        return None  # Not a chunk file — use load_blueprint instead
    if "chunk" in data and "files" in data:
        return data
    return None


# --------------------------------------------------------------------------------
# Indexer
# --------------------------------------------------------------------------------

@dataclass
class IndexStats:
    """Statistics from an indexing run."""
    functions_indexed: int = 0
    classes_indexed: int = 0
    documents_created: int = 0
    skipped: int = 0  # Phase 7 — repos skipped (no change since last index)


class BlueprintIndexer:
    """Converts one or more blueprints into txtai-indexable documents and
    loads them into a :class:`TxtaiClient` index.

    Example::

        client = TxtaiClient(index_dir=Path("./data/txtai"))
        indexer = BlueprintIndexer(client)

        stats = indexer.index_blueprint(blueprint)
        print(f"Indexed {stats.documents_created} documents")

        client.save()

        # ... later:
        results = client.search("authentication middleware")
    """

    def __init__(self, client: TxtaiClient) -> None:
        self.client = client
        self._stats = IndexStats()
        self._last_indexed: Optional[str] = None
        self._last_modified: Optional[str] = None

    def index_blueprint(
        self,
        blueprint: Blueprint,
        chunk_id: int = 0,
        *,
        include_bodies: bool = True,
    ) -> IndexStats:
        """Index every function and class from a single :class:`Blueprint`.

        Args:
            blueprint: Source blueprint to index.
            chunk_id: Chunk number this blueprint represents (for multi-chunk repos).
            include_bodies: If True, include truncated function bodies in the
                            embedded text (more context, larger index).

        Returns:
            IndexStats with counts of indexed items.
        """
        docs: List[Dict[str, Any]] = []

        for func in blueprint.functions:
            text = _build_text(func)
            if not include_bodies:
                # Strip body before passing to avoid bloating the index
                text = text.replace(f"body: {func.body[:500]}", "body: ...")
            docs.append({
                "id": _function_uid(blueprint.repo, func, chunk_id),
                "text": text,
                "repo": blueprint.repo,
                "language": blueprint.language,
                "kind": "function",
                "name": func.name,
                "signature": func.signature,
                "file": str(func.file),
                "line": func.line,
                "docstring": _truncate(func.docstring),
                "decorators": func.decorators or [],
                "chunk_id": chunk_id,
            })
            self._stats.functions_indexed += 1

        for ds in blueprint.data_structures:
            docs.append({
                "id": _ds_uid(blueprint.repo, ds, chunk_id),
                "text": _build_text_for_ds(ds),
                "repo": blueprint.repo,
                "language": blueprint.language,
                "kind": "class",
                "name": ds.name,
                "signature": "",
                "file": str(ds.file),
                "line": ds.line,
                "docstring": _truncate(ds.docstring),
                "decorators": [],
                "chunk_id": chunk_id,
            })
            self._stats.classes_indexed += 1

        if docs:
            self.client.index(docs)
            self._stats.documents_created += len(docs)

        return self._stats

    def index_blueprint_from_yaml(
        self,
        yaml_path: Path,
        chunk_id: int = 0,
    ) -> IndexStats:
        """Load a YAML blueprint and index it in one step.

        Handles both modern full blueprints (``{source, blueprint}``) and
        legacy chunk files (``{chunk, files, total_chunks}``).

        For legacy chunk files, functions are NOT re-extracted (the chunk files
        only contain file lists, not function data). The chunk file is skipped
        for indexing purposes — the parent repo's full blueprint should be
        used instead.

        Args:
            yaml_path: Path to a saved ``.yaml`` blueprint file.
            chunk_id: Chunk number (for chunked repos).

        Returns:
            IndexStats for the run (may be zero docs if file was a chunk file).
        """
        from repo_transmute.blueprint.storage import (
            load_blueprint,
            get_blueprint_last_modified,
        )

        # Check if this is a legacy chunk file (not a full blueprint)
        chunk_data = _load_chunk_file(yaml_path)
        if chunk_data is not None:
            # Legacy chunk file — skip, function data not present
            # The parent repo's full blueprint (if re-ingested) should be indexed instead
            return self._stats

        blueprint = load_blueprint(yaml_path)
        last_modified = get_blueprint_last_modified(yaml_path)
        return self.index_blueprint(blueprint, chunk_id=chunk_id)

    def index_directory(
        self,
        blueprints_dir: Path,
        glob_pattern: str = "*.yaml",
        *,
        skip_unchanged: bool = True,
    ) -> IndexStats:
        """Index all blueprint YAML files in a directory.

        Detects chunked blueprints (e.g. ``open-notebook.chunk10.yaml``) and
        extracts the chunk id from the filename.

        When ``skip_unchanged=True`` (default, Phase 7), each repo is skipped
        if its ``last_modified`` timestamp matches the value recorded during
        the last indexing run — meaning no new commits have landed since.

        Args:
            blueprints_dir: Directory containing YAML blueprint files.
            glob_pattern: Glob pattern for files to index.
            skip_unchanged: If True, skip repos whose blueprints haven't
                           changed since the last indexing run.

        Returns:
            Merged IndexStats across all indexed files.
        """
        from repo_transmute.blueprint.storage import get_blueprint_last_modified

        # Separate full blueprints from legacy chunk files.
        # Full blueprints are indexed; legacy chunk files are skipped
        # (they contain file lists only, not function data).
        full_bp_files: List[Path] = []
        legacy_chunk_files: List[Path] = []

        for path in sorted(blueprints_dir.glob(glob_pattern)):
            chunk_data = _load_chunk_file(path)
            if chunk_data is not None:
                legacy_chunk_files.append(path)
            else:
                full_bp_files.append(path)

        # Group full blueprints by repo
        repo_full_bps: Dict[str, List[tuple]] = {}
        for path in full_bp_files:
            name = path.stem  # e.g. "HKUDS__nanobot" or "lfnovo__open-notebook"
            repo = name
            chunk_id = 0
            if "." in name:
                maybe_chunk = name.rsplit(".", 1)[-1]
                if maybe_chunk.startswith("chunk"):
                    repo = name[: -(len(maybe_chunk) + 1)]
                    try:
                        chunk_id = int(maybe_chunk[len("chunk"):])
                    except ValueError:
                        pass
            if repo not in repo_full_bps:
                repo_full_bps[repo] = []
            repo_full_bps[repo].append((path, chunk_id))

        # Record the indexing timestamp once per run
        self._last_indexed = datetime.utcnow().isoformat() + "Z"

        for repo, chunks in sorted(repo_full_bps.items()):
            # Check if this repo has changed since last index
            if skip_unchanged:
                yaml_path_for_meta = chunks[0][0]
                last_modified = get_blueprint_last_modified(yaml_path_for_meta)
                prev_indexed = self.client.get_repo_last_indexed(repo)
                prev_modified = self.client.get_repo_last_modified(repo)

                if prev_indexed is not None and prev_modified == last_modified:
                    # Repo content is unchanged — skip all its chunks
                    self._stats.skipped += 1
                    continue

                self._last_modified = last_modified
            else:
                self._last_modified = None

            for yaml_path, chunk_id in chunks:
                try:
                    self.index_blueprint_from_yaml(yaml_path, chunk_id=chunk_id)
                except Exception:
                    # Let the caller decide how to handle individual file errors
                    raise

            # Record last_indexed for this repo after all its chunks are done
            self.client.set_repo_last_indexed(
                repo=repo,
                last_indexed=self._last_indexed,
                last_modified=self._last_modified,
            )

        return self._stats

    def stats(self) -> IndexStats:
        """Return cumulative stats since this indexer was created."""
        return self._stats
