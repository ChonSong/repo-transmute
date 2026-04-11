#!/usr/bin/env python3
"""
reingest_stale_repos.py — re-ingest repos flagged as stale by check_repos_stale.py.

Reads data/_repo_stale_status.json (written by check_repos_stale.py).
Writes re-ingest results to data/_repo_reingest_status.json.
Exits 0; prints REINGEST_DONE|<count> on success, REINGEST_SKIP|0 if no stale repos.
"""
import subprocess
import sys
import json
import shutil
import os
from pathlib import Path

REPO_TRANSMUTE = Path(__file__).parent.parent
CACHE_DIR = REPO_TRANSMUTE / "data" / "cache"
STATUS_FILE = REPO_TRANSMUTE / "data" / "_repo_stale_status.json"
RESULT_FILE = REPO_TRANSMUTE / "data" / "_repo_reingest_status.json"


def reingest_repo(repo: str, cache_dir: Path) -> dict:
    """Re-ingest a single repo using repo-transmute ingest."""
    owner, name = repo.split("/", 1)
    repo_dest = cache_dir / f"{owner}__{name}"

    # Remove existing cached copy for clean re-ingest
    if repo_dest.exists():
        shutil.rmtree(repo_dest)

    try:
        # Run repo-transmute ingest
        result = subprocess.run(
            [
                sys.executable, "-m", "repo_transmute.cli",
                "ingest", repo,
                "--cache-dir", str(cache_dir),
                "--target", "typescript",
            ],
            cwd=REPO_TRANSMUTE,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min timeout per repo
        )
        success = result.returncode == 0
        return {
            "repo": repo,
            "success": success,
            "stdout": result.stdout[-500:] if result.stdout else "",
            "stderr": result.stderr[-500:] if result.stderr else "",
        }
    except Exception as e:
        return {
            "repo": repo,
            "success": False,
            "error": str(e),
        }


def main():
    # Read stale repos from previous step
    if not STATUS_FILE.exists():
        print("REINGEST_SKIP|0  (no stale status file — run check_repos_stale.py first)")
        _write_result("SKIP", [])
        return 0

    with open(STATUS_FILE) as f:
        stale_data = json.load(f)

    stale_repos = stale_data.get("stale_repos", [])
    if not stale_repos:
        print("REINGEST_SKIP|0")
        _write_result("SKIP", [])
        return 0

    results = []
    for entry in stale_repos:
        repo = entry["repo"]
        print(f"Re-ingesting {repo}...")
        result = reingest_repo(repo, CACHE_DIR)
        results.append(result)
        status = "✓" if result["success"] else "✗"
        print(f"  {status} {repo}: {'OK' if result['success'] else result.get('error', 'FAILED')}")

    success_count = sum(1 for r in results if r["success"])
    _write_result("DONE", results)
    print(f"REINGEST_DONE|{success_count}/{len(results)}")
    return 0


def _write_result(status: str, results: list):
    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULT_FILE, "w") as f:
        json.dump({"status": status, "reingests": results}, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
