"""Blueprint indexer — convert RepoTransmute blueprints into indexable txtai documents."""

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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
# Indexer
# --------------------------------------------------------------------------------

@dataclass
class IndexStats:
    """Statistics from an indexing run."""
    functions_indexed: int = 0
    classes_indexed: int = 0
    documents_created: int = 0


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

        Args:
            yaml_path: Path to a saved ``.yaml`` blueprint file.
            chunk_id: Chunk number (for chunked repos).

        Returns:
            IndexStats for the run.
        """
        from repo_transmute.blueprint.storage import load_blueprint
        blueprint = load_blueprint(yaml_path)
        return self.index_blueprint(blueprint, chunk_id=chunk_id)

    def index_directory(
        self,
        blueprints_dir: Path,
        glob_pattern: str = "*.yaml",
    ) -> IndexStats:
        """Index all blueprint YAML files in a directory.

        Detects chunked blueprints (e.g. ``open-notebook.chunk10.yaml``) and
        extracts the chunk id from the filename.

        Args:
            blueprints_dir: Directory containing YAML blueprint files.
            glob_pattern: Glob pattern for files to index.

        Returns:
            Merged IndexStats across all indexed files.
        """
        for path in sorted(blueprints_dir.glob(glob_pattern)):
            chunk_id = 0
            name = path.stem  # e.g. "open-notebook.chunk10"
            # Detect chunk id from filename like open-notebook.chunk10
            if "." in name:
                maybe_chunk = name.rsplit(".", 1)[-1]
                if maybe_chunk.startswith("chunk"):
                    try:
                        chunk_id = int(maybe_chunk[len("chunk"):])
                    except ValueError:
                        pass

            self.index_blueprint_from_yaml(path, chunk_id=chunk_id)

        return self._stats

    def stats(self) -> IndexStats:
        """Return cumulative stats since this indexer was created."""
        return self._stats
