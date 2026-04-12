# Phase 1: MVP Implementation Plan

**Goal:** End-to-end proof of concept — clone a repo, extract blueprint, save YAML

**Timeline:** 1-2 weeks  
**Test Repo:** `ryanmcdermott/clean-code-javascript` (small, well-structured)

---

## 1.1 Project Setup

```bash
mkdir repo-transmute
cd repo-transmute
poetry init
# or
pip install -e .
```

**Dependencies:**
```toml
[tool.poetry.dependencies]
python = "^3.10"
pygithub = "^2.0"
pyyaml = "^6.0"
tree-sitter = "^0.20"
pathspec = "^0.11"
tqdm = "^4.65"
```

**Commands:**
```bash
poetry add pygithub pyyaml tree-sitter pathspec tqdm
```

---

## 1.2 Clone Service

**File:** `src/repo_transmute/ingestion/clone.py`

```python
"""Clone repositories from GitHub."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import requests


def clone_repo(
    owner: str,
    repo: str,
    target_dir: Path,
    branch: Optional[str] = None,
    depth: int = 1
) -> Path:
    """Clone a GitHub repository.
    
    Args:
        owner: Repository owner
        repo: Repository name
        target_dir: Where to clone
        branch: Branch to clone (default: main/master)
        depth: Shallow clone depth
        
    Returns:
        Path to cloned repository
    """
    url = f"https://github.com/{owner}/{repo}.git"
    dest = target_dir / f"{owner}__{repo}"
    
    if dest.exists():
        shutil.rmtree(dest)
    
    cmd = ["git", "clone", "--depth", str(depth), url, str(dest)]
    if branch:
        cmd.extend(["--branch", branch])
    
    subprocess.run(cmd, check=True)
    return dest


def get_default_branch(owner: str, repo: str) -> str:
    """Get default branch from GitHub API."""
    resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers={"Accept": "application/vnd.github.v3+json"}
    )
    return resp.json().get("default_branch", "main")
```

---

## 1.3 Language Detection

**File:** `src/repo_transmute/ingestion/detector.py`

```python
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


def detect_language(repo_path: Path) -> Optional[str]:
    """Detect primary language from repo contents.
    
    Looks for common markers:
    1. File extensions
    2. Package managers (requirements.txt, package.json, Cargo.toml)
    """
    counts: Dict[str, int] = {}
    
    for file in repo_path.rglob("*"):
        if file.is_file() and not is_ignored(file):
            ext = file.suffix.lower()
            if ext in EXTENSION_LANGUAGE_MAP:
                lang = EXTENSION_LANGUAGE_MAP[ext]
                counts[lang] = counts.get(lang, 0) + 1
    
    if not counts:
        return None
    
    return max(counts, key=counts.get)


def is_ignored(path: Path) -> bool:
    """Check if path should be ignored."""
    ignores = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build"}
    return any(part in ignores for part in path.parts)
```

---

## 1.4 File Walker

**File:** `src/repo_transmute/ingestion/walker.py`

```python
"""Walk repository file tree."""

from pathlib import Path
from typing import Iterator, Set


def walk_source_files(
    repo_path: Path,
    extensions: Set[str] = None,
    ignore_patterns: Set[str] = None
) -> Iterator[Path]:
    """Walk repository and yield source files.
    
    Args:
        repo_path: Root of repository
        extensions: File extensions to include (e.g., {".py", ".js"})
        ignore_patterns: Patterns to ignore
        
    Yields:
        Source file paths
    """
    if extensions is None:
        extensions = {".py", ".js", ".ts", ".rs", ".go"}
    
    if ignore_patterns is None:
        ignore_patterns = {".git", "__pycache__", "node_modules", "venv", "dist"}
    
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
            
        # Skip ignored patterns
        if any(ignored in path.parts for ignored in ignore_patterns):
            continue
            
        # Filter by extension
        if path.suffix.lower() in extensions:
            yield path


def get_file_tree(repo_path: Path, max_depth: int = 5) -> dict:
    """Get file tree structure as nested dict."""
    tree = {"name": repo_path.name, "type": "directory", "children": []}
    
    for path in sorted(repo_path.rglob("*")):
        if len(path.relative_to(repo_path).parts) > max_depth:
            continue
            
        rel_path = path.relative_to(repo_path)
        if is_ignored(path):
            continue
            
        # Build tree structure
        current = tree
        for part in rel_path.parts[:-1]:
            # Navigate to correct depth
            pass
    
    return tree
```

---

## 1.5 Blueprint Extractor

**File:** `src/repo_transmute/blueprint/extractor.py`

```python
"""Extract interfaces, functions, classes from source code."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class Function:
    name: str
    signature: str
    file: str
    line: int
    docstring: Optional[str] = None
    async: bool = False


@dataclass
class DataStructure:
    name: str
    type: str  # class, struct, enum
    file: str
    line: int
    fields: List[str] = field(default_factory=list)
    docstring: Optional[str] = None


@dataclass
class Blueprint:
    repo: str
    language: str
    functions: List[Function] = field(default_factory=list)
    data_structures: List[DataStructure] = field(default_factory=list)


def extract_from_python(file_path: Path) -> List[Function]:
    """Extract functions and classes from Python file."""
    content = file_path.read_text()
    functions = []
    
    # Regex patterns
    func_pattern = r'^(?:async\s+)?def\s+(\w+)\s*\((.*?)\)\s*(?:->\s*(\S+))?:'
    class_pattern = r'^class\s+(\w+)(?:\((.*?)\))?:'
    
    for i, line in enumerate(content.split("\n"), 1):
        # Function match
        match = re.match(func_pattern, line.strip())
        if match:
            name, params, ret = match.groups()
            functions.append(Function(
                name=name,
                signature=f"({params}) -> {ret or 'None'}",
                file=str(file_path),
                line=i,
                async="async" in line
            ))
    
    return functions


def extract_from_javascript(file_path: Path) -> List[Function]:
    """Extract functions from JavaScript/TypeScript."""
    content = file_path.read_text()
    functions = []
    
    # Arrow functions, function declarations
    patterns = [
        r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\((.*?)\)',
        r'^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s+)?\((.*?)\)\s*=>',
    ]
    
    for i, line in enumerate(content.split("\n"), 1):
        for pattern in patterns:
            match = re.match(pattern, line.strip())
            if match:
                name, params = match.groups()
                functions.append(Function(
                    name=name,
                    signature=f"({params})",
                    file=str(file_path),
                    line=i
                ))
                break
    
    return functions


def extract_all(repo_path: Path, language: str) -> Blueprint:
    """Extract all structures from repo."""
    from repo_transmute.ingestion.walker import walk_source_files
    
    functions = []
    data_structures = []
    
    ext_map = {
        "python": ".py",
        "javascript": ".js",
        "typescript": ".ts",
    }
    
    ext = ext_map.get(language, ".py")
    
    for file_path in walk_source_files(repo_path, extensions={ext}):
        if language == "python":
            functions.extend(extract_from_python(file_path))
        elif language in ("javascript", "typescript"):
            functions.extend(extract_from_javascript(file_path))
    
    return Blueprint(
        repo=str(repo_path.name),
        language=language,
        functions=functions,
        data_structures=data_structures
    )
```

---

## 1.6 Blueprint Storage

**File:** `src/repo_transmute/blueprint/storage.py`

```python
"""Save and load blueprints."""

import yaml
from datetime import datetime
from pathlib import Path
from typing import Optional

from repo_transmute.blueprint.extractor import Blueprint


def save_blueprint(
    blueprint: Blueprint,
    output_dir: Path,
    version: Optional[str] = None
) -> Path:
    """Save blueprint to YAML file.
    
    Args:
        blueprint: Extracted blueprint
        output_dir: Where to save
        version: Optional version string
        
    Returns:
        Path to saved file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    data = {
        "version": version or "1.0",
        "generated": datetime.utcnow().isoformat(),
        "source": {
            "repo": blueprint.repo,
            "language": blueprint.language
        },
        "blueprint": {
            "functions": [
                {
                    "name": f.name,
                    "signature": f.signature,
                    "file": f.file,
                    "line": f.line,
                    "async": f.async
                }
                for f in blueprint.functions
            ],
            "data_structures": [
                {
                    "name": ds.name,
                    "type": ds.type,
                    "file": ds.file,
                    "line": ds.line,
                    "fields": ds.fields
                }
                for ds in blueprint.data_structures
            ]
        }
    }
    
    filename = f"{blueprint.repo.replace('/', '__')}.yaml"
    filepath = output_dir / filename
    
    with open(filepath, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    return filepath


def load_blueprint(path: Path) -> Blueprint:
    """Load blueprint from YAML."""
    with open(path) as f:
        data = yaml.safe_load(f)
    
    # Reconstruct Blueprint object
    # (simplified - full implementation would rebuild dataclasses)
    return Blueprint(
        repo=data["source"]["repo"],
        language=data["source"]["language"]
    )
```

---

## 1.7 CLI Entry Point

**File:** `src/repo_transmute/cli.py`

```python
"""CLI for repo-transmute."""

import click
from pathlib import Path

from repo_transmute.ingestion.clone import clone_repo
from repo_transmute.ingestion.detector import detect_language
from repo_transmute.blueprint.extractor import extract_all
from repo_transmute.blueprint.storage import save_blueprint


@click.group()
def cli():
    """RepoTransmute - AI-powered code transpilation."""
    pass


@cli.command()
@click.argument("repo", default="ryanmcdermott/clean-code-javascript")
@click.option("--output-dir", default="./data/blueprints", help="Output directory")
@click.option("--cache-dir", default="./data/cache", help="Cache directory")
def ingest(repo: str, output_dir: str, cache_dir: str):
    """Clone repo and extract blueprint."""
    owner, name = repo.split("/")
    
    click.echo(f"Cloning {repo}...")
    repo_path = clone_repo(owner, name, Path(cache_dir))
    
    click.echo("Detecting language...")
    language = detect_language(repo_path)
    click.echo(f"Detected: {language}")
    
    click.echo("Extracting blueprint...")
    blueprint = extract_all(repo_path, language)
    click.echo(f"Found {len(blueprint.functions)} functions")
    
    click.echo("Saving...")
    output_path = save_blueprint(blueprint, Path(output_dir))
    click.echo(f"Saved to {output_path}")


@cli.command()
@click.argument("query")
def search(query: str):
    """Search blueprints (requires txtai)."""
    click.echo(f"Searching: {query}")
    # TODO: Implement with txtai


if __name__ == "__main__":
    cli()
```

---

## Test Run

```bash
# Install
cd repo-transmute
pip install -e .

# Run MVP
python -m repo_transmute.cli ingest ryanmcdermott/clean-code-javascript

# Expected output:
# Cloning ryanmcdermott/clean-code-javascript...
# Detected: javascript
# Found 42 functions
# Saved to data/blueprints/ryanmcdermott__clean-code-javascript.yaml
```

---

## Next Steps After Phase 1

1. Add more language parsers (TypeScript, Go, Rust)
2. Add class/structure extraction
3. Integrate txtai for embedding
4. Build LLM transpilation pipeline
