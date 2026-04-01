"""Clone repositories from GitHub."""

import os
import shutil
import subprocess
from datetime import datetime
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


def get_last_commit_time(repo_path: Path) -> Optional[str]:
    """Return the ISO-8601 timestamp of the most recent commit in a repo.

    Used for Phase 7 deduplication — a repo is skipped on re-indexing if its
    last commit time matches the recorded value from the previous run.

    Args:
        repo_path: Path to a cloned git repository

    Returns:
        ISO-8601 string (e.g. "2026-03-31T14:30:00Z") or None on error.
    """
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI"],
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            ts = result.stdout.strip()
            # Normalise to UTC "Z" suffix if git already returns ISO
            return ts or None
    except Exception:
        pass
    return None


def get_git_log_since(repo_path: Path, since: Optional[str] = None) -> subprocess.CompletedProcess:
    """Run ``git log --since=<timestamp>`` and return the result.

    Args:
        repo_path: Path to a cloned git repository
        since: ISO-8601 timestamp (passed to git's ``--since`` flag)

    Returns:
        subprocess.CompletedProcess with stdout/stderr/returncode
    """
    cmd = ["git", "log", "--format=%H %cI"]
    if since:
        cmd.append(f"--since={since}")
    return subprocess.run(
        cmd,
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        timeout=30,
    )
