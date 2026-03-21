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
    
    subprocess.run(cmd, check=True, capture_output=True)
    return dest


def get_default_branch(owner: str, repo: str) -> str:
    """Get default branch from GitHub API."""
    resp = requests.get(
        f"https://api.github.com/repos/{owner}/{repo}",
        headers={"Accept": "application/vnd.github.v3+json"}
    )
    return resp.json().get("default_branch", "main")
