"""Git clone with branch/tag handling."""

from __future__ import annotations

import subprocess
from pathlib import Path


def clone_repo(
    repo: str,
    cache_dir: Path,
    branch: str | None = None,
    depth: int = 1,
) -> Path:
    """Clone a git repository.
    
    Args:
        repo: GitHub repo in format 'owner/name'
        cache_dir: Directory to clone into
        branch: Optional branch/tag to checkout
        depth: Clone depth (1 for latest only)
    
    Returns:
        Path to cloned repo
    """
    if "/" not in repo:
        raise ValueError(f"Invalid repo format: {repo}. Use 'owner/name'")
    
    owner, name = repo.split("/", 1)
    repo_dir = cache_dir / f"{owner}__{name}"
    url = f"https://github.com/{repo}.git"
    
    if repo_dir.exists() and (repo_dir / ".git").exists():
        # Already cloned — pull latest
        subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=repo_dir,
            capture_output=True,
            check=True,
        )
        if branch:
            subprocess.run(
                ["git", "checkout", branch],
                cwd=repo_dir,
                capture_output=True,
                check=True,
            )
        return repo_dir
    
    cmd = ["git", "clone", "--depth", str(depth)]
    if branch:
        cmd.extend(["--branch", branch])
    cmd.extend([url, str(repo_dir)])
    
    subprocess.run(cmd, capture_output=True, check=True)
    return repo_dir


def clone_local_path(path: Path) -> Path:
    """Return the local path as-is (no cloning needed)."""
    resolved = path.resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    return resolved
