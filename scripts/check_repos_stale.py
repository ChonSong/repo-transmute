#!/usr/bin/env python3
"""
check_repos_stale.py — detect which cached repos have new commits on remote.

Reads no stdin.  Exits 0 and prints:
  STALE|<count>  — one or more stale repos found
  CLEAN|0        — all repos up-to-date
  ERROR|<msg>    — on unexpected errors (always proceeds to next step)

Writes stale repos list to data/_repo_stale_status.json so downstream
steps can re-ingest only what changed.
"""
import subprocess
import sys
import json
import os
from pathlib import Path

REPO_TRANSMUTE = Path(__file__).parent.parent
CACHE_DIR = REPO_TRANSMUTE / "data" / "cache"
STATUS_FILE = REPO_TRANSMUTE / "data" / "_repo_stale_status.json"


def get_cached_repos():
    """Return list of (owner__name, Path) for cached repos."""
    if not CACHE_DIR.exists():
        return []
    return [(p.name, p) for p in CACHE_DIR.iterdir() if p.is_dir() and "__" in p.name]


def get_remote_head_time(repo_path: Path) -> str | None:
    """Get commit time of remote HEAD (fetched ref).
    Returns ISO-8601 string or None on failure.
    """
    try:
        # Ensure remote refs are available
        subprocess.run(
            ["git", "fetch", "--quiet", "origin", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            timeout=60,
        )
        # Get the commit time of origin/HEAD
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ci", "origin/HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def get_local_head_time(repo_path: Path) -> str | None:
    """Get commit time of local HEAD. Returns ISO-8601 string or None."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ci", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def check_repo_stale(name: str, repo_path: Path) -> dict | None:
    """Check if a single repo is stale. Returns dict if stale, None if clean."""
    remote_time = get_remote_head_time(repo_path)
    local_time = get_local_head_time(repo_path)

    if remote_time is None:
        # Can't determine — assume clean to avoid unnecessary re-ingests
        return None

    # Compare by commit time (datetime parsing)
    from datetime import datetime
    try:
        remote_dt = datetime.fromisoformat(remote_time.replace("Z", "+00:00"))
        local_dt = datetime.fromisoformat(local_time.replace("Z", "+00:00")) if local_time else None

        if local_dt is None or remote_dt > local_dt:
            return {
                "repo": name.replace("__", "/"),
                "cache_path": str(repo_path),
                "local_head": local_time,
                "remote_head": remote_time,
            }
    except Exception:
        pass
    return None


def main():
    cached = get_cached_repos()
    if not cached:
        print("CLEAN|0")
        _write_status("CLEAN", [])
        return 0

    stale_repos = []
    errors = []

    for name, path in cached:
        try:
            stale = check_repo_stale(name, path)
            if stale:
                stale_repos.append(stale)
        except Exception as e:
            errors.append({"repo": name, "error": str(e)})

    status = "STALE" if stale_repos else "CLEAN"
    count = len(stale_repos)

    _write_status(status, stale_repos, errors=errors)

    print(f"{status}|{count}")
    for s in stale_repos:
        print(f"  {s['repo']}: remote={s['remote_head']} local={s.get('local_head', 'none')}")

    return 0


def _write_status(status: str, stale_repos: list, errors: list | None = None):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "status": status,
        "stale_repos": stale_repos,
        "errors": errors or [],
    }
    with open(STATUS_FILE, "w") as f:
        json.dump(data, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
