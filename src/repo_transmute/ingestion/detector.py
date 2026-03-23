"""Detect programming language from repository."""

from pathlib import Path
from typing import Optional, Dict


EXTENSION_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
}


# Common ignore patterns
IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".idea", ".vscode"}


def detect_language(repo_path: Path) -> Optional[str]:
    """Detect primary language from repo contents.
    
    Looks for common markers:
    1. File extensions
    2. Package managers (requirements.txt, package.json, Cargo.toml)
    """
    counts: Dict[str, int] = {}
    
    for file in repo_path.rglob("*"):
        if file.is_file() and not _is_ignored(file):
            ext = file.suffix.lower()
            if ext in EXTENSION_LANGUAGE_MAP:
                lang = EXTENSION_LANGUAGE_MAP[ext]
                counts[lang] = counts.get(lang, 0) + 1
    
    if not counts:
        # Check for package managers as fallback
        return _detect_from_package_managers(repo_path)
    
    return max(counts, key=counts.get)


def _detect_from_package_managers(repo_path: Path) -> Optional[str]:
    """Detect language from package manager files."""
    pkg_files = {
        "requirements.txt": "python",
        "setup.py": "python",
        "pyproject.toml": "python",
        "package.json": "javascript",
        "Cargo.toml": "rust",
        "go.mod": "go",
        "pom.xml": "java",
        "Gemfile": "ruby",
    }
    
    for filename, lang in pkg_files.items():
        if (repo_path / filename).exists():
            return lang
    
    return None


def _is_ignored(path: Path) -> bool:
    """Check if path should be ignored."""
    return any(part in IGNORE_DIRS for part in path.parts)
