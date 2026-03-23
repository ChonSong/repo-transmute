"""Walk repository file tree."""

from pathlib import Path
from typing import Iterator, Set, Optional


# Default ignore patterns
DEFAULT_IGNORES = {".git", "__pycache__", "node_modules", "venv", "dist", "build", ".venv", ".idea", ".vscode", "*.pyc"}

# Default source extensions
DEFAULT_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".rs", ".go", ".java", ".c", ".cpp", ".cs", ".rb", ".php", ".swift", ".kt", ".scala"}


def walk_source_files(
    repo_path: Path,
    extensions: Optional[Set[str]] = None,
    ignore_patterns: Optional[Set[str]] = None
) -> Iterator[Path]:
    """Walk repository and yield source files.
    
    Args:
        repo_path: Root of repository
        extensions: File extensions to include
        ignore_patterns: Patterns to ignore
        
    Yields:
        Source file paths
    """
    if extensions is None:
        extensions = DEFAULT_EXTENSIONS
    
    if ignore_patterns is None:
        ignore_patterns = DEFAULT_IGNORES
    
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
            
        # Skip ignored patterns
        if any(ignored in path.parts for ignored in ignore_patterns):
            continue
        
        # Skip hidden files
        if path.name.startswith("."):
            continue
            
        # Filter by extension
        if path.suffix.lower() in extensions:
            yield path


def get_relative_path(path: Path, repo_root: Path) -> Path:
    """Get path relative to repo root."""
    try:
        return path.relative_to(repo_root)
    except ValueError:
        return path
