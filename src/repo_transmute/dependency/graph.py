"""Dependency resolution for TypeScript/JavaScript module graphs."""

import re
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Set


# Regex patterns for various import/export syntaxes.
# Order matters: more specific patterns should come before general ones.
IMPORT_REGEXES = [
    # import * as X from 'Y'  (wildcard namespace import — before named import)
    re.compile(r"import\s+\*\s+as\s+[\w]+\s+from\s+['\"]([^'\"]+)['\"]"),
    # import { X, Y, Z } from 'Y'  (named imports)
    re.compile(r"import\s+\{[^}]+\}\s+from\s+['\"]([^'\"]+)['\"]"),
    # import X from 'Y'  (default import)
    re.compile(r"import\s+[\w]+\s+from\s+['\"]([^'\"]+)['\"]"),
    # import('Y') / import("Y") — dynamic imports
    re.compile(r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"),
    # export { X } from 'Y' / export * from 'Y' — re-exports
    re.compile(r"export\s+(?:\{[^}]+\}|\*)\s+from\s+['\"]([^'\"]+)['\"]"),
    # require('Y') / require("Y") — CommonJS
    re.compile(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"),
]


def parse_imports(file_path: Path) -> List[str]:
    """
    Parse TypeScript/JavaScript import/export statements from a file.

    Matches:
    - import X from 'Y'
    - import { X, Y } from 'Z'
    - import * as X from 'Y'
    - import('Y') - dynamic imports
    - export from 'Y'
    - export * from 'Y'
    - require('Y')

    Args:
        file_path: Path to the .ts/.js file

    Returns:
        List of imported module paths
    """
    imports = []

    try:
        content = file_path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return imports

    # Remove comments to avoid false positives
    # Remove single-line comments
    content = re.sub(r"//.*?$", "", content, flags=re.MULTILINE)
    # Remove multi-line comments
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)

    for pattern in IMPORT_REGEXES:
        for match in pattern.finditer(content):
            module = match.group(1)
            # Include all imports (relative and external)
            imports.append(module)

    return imports


class DependencyGraph:
    """Build and query module dependency relationships."""

    def __init__(self, root: Optional[Path] = None):
        self.root = root
        self.nodes: Dict[Path, List[str]] = {}  # file -> imports
        self.reverse: Dict[Path, Set[Path]] = {}  # file -> imported_by

    def add_file(self, path: Path, imports: List[str]) -> None:
        """Add a file and its imports to the graph."""
        path = path.resolve() if path.is_absolute() else path
        self.nodes[path] = imports

    def resolve_import(self, import_path: Path, importer: Path) -> Optional[Path]:
        """Try to resolve an import path to an actual file."""
        if self.root is None:
            return None

        if str(import_path).startswith("."):
            base = importer.parent
            for ext in (
                ".ts", ".tsx", ".js", ".jsx",
                "/index.ts", "/index.js", "/index.tsx", "/index.jsx",
            ):
                if ext.startswith("/"):
                    candidate = base / import_path / ext[1:]
                else:
                    candidate = (base / import_path).with_suffix(ext)
                if candidate.exists():
                    return candidate.resolve()
            return None

        return None

    def get_import_order(self) -> List[Path]:
        """Get files in topological order (dependencies first).

        Returns:
            List of file paths in dependency order
        """
        in_degree: Dict[Path, int] = {node: 0 for node in self.nodes}
        adjacency: Dict[Path, List[Path]] = {node: [] for node in self.nodes}

        for file_path in self.nodes:
            for imp in self.nodes[file_path]:
                resolved = self.resolve_import(Path(imp), file_path)
                if resolved and resolved in self.nodes:
                    adjacency[resolved].append(file_path)
                    in_degree[file_path] += 1

        queue = [node for node in self.nodes if in_degree[node] == 0]
        result = []

        while queue:
            queue.sort(key=str)
            node = queue.pop(0)
            result.append(node)
            for neighbor in adjacency[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        result.extend([n for n in self.nodes if n not in result])
        return result

    def get_chunk(self, entry: Path, max_size: int = 30) -> List[Path]:
        """Get a chunk of files starting from entry point.

        Args:
            entry: Entry point file path
            max_size: Maximum number of files in chunk

        Returns:
            List of file paths in the chunk
        """
        entry = entry.resolve() if entry.is_absolute() else entry

        if entry not in self.nodes:
            return [entry]

        visited: Set[Path] = set()
        queue = [entry]
        chunk = []

        while queue and len(chunk) < max_size:
            queue.sort(key=str)
            current = queue.pop(0)

            if current in visited:
                continue

            visited.add(current)
            chunk.append(current)

            if current in self.nodes:
                for imp in self.nodes[current]:
                    resolved = self.resolve_import(Path(imp), current)
                    if resolved and resolved in self.nodes and resolved not in visited:
                        queue.append(resolved)

            if current in self.reverse:
                for dependent in self.reverse[current]:
                    if dependent not in visited:
                        queue.append(dependent)

        return chunk


class ProcessQueue:
    """Queue system for processing repositories in dependency order."""

    def __init__(self, db_path: str = "data/transmute.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite database."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS queue (
                repo TEXT PRIMARY KEY,
                priority INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def add(self, repo: str, priority: int = 0) -> None:
        """Add a repository to the queue.

        Args:
            repo: Repository identifier (e.g., 'owner/repo')
            priority: Higher priority = processed first (default 0)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT status FROM queue WHERE repo = ?", (repo,))
        row = cursor.fetchone()

        if row is None:
            cursor.execute(
                "INSERT INTO queue (repo, priority, status) VALUES (?, ?, 'pending')",
                (repo, priority),
            )
        else:
            current_status = row[0]
            new_status = "pending" if current_status == "completed" else current_status
            cursor.execute(
                "UPDATE queue SET priority = ?, status = ? WHERE repo = ?",
                (priority, new_status, repo),
            )

        conn.commit()
        conn.close()

    def get_next(self) -> Optional[dict]:
        """Get the next repository to process.

        Returns:
            Dict with repo, priority, status or None if queue is empty
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT repo, priority, status, created_at
            FROM queue
            WHERE status = 'pending'
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return {
            "repo": row[0],
            "priority": row[1],
            "status": row[2],
            "created_at": row[3],
        }

    def mark_complete(self, repo: str) -> None:
        """Mark a repository as completed."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE queue SET status = 'completed', completed_at = CURRENT_TIMESTAMP WHERE repo = ?",
            (repo,),
        )
        conn.commit()
        conn.close()

    def get_status(self, repo: str) -> Optional[dict]:
        """Get the status of a repository."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT repo, priority, status, created_at, completed_at FROM queue WHERE repo = ?",
            (repo,),
        )
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return {
            "repo": row[0],
            "priority": row[1],
            "status": row[2],
            "created_at": row[3],
            "completed_at": row[4],
        }

    def list_pending(self) -> List[dict]:
        """List all pending repositories."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT repo, priority, status, created_at FROM queue WHERE status = 'pending' ORDER BY priority DESC, created_at ASC"
        )
        rows = cursor.fetchall()
        conn.close()

        return [
            {"repo": r[0], "priority": r[1], "status": r[2], "created_at": r[3]}
            for r in rows
        ]
