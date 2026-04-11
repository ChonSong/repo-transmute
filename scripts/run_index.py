#!/usr/bin/env python3
"""
run_index.py — run TXTAI indexer on data/blueprints/.

Always runs (no circuit-breaker gate) since re-indexing is cheap if nothing changed.
Writes stats to data/_repo_index_status.json.
Exits 0 on success, 1 on failure.
"""
import subprocess
import sys
import json
import re
from pathlib import Path

REPO_TRANSMUTE = Path(__file__).parent.parent
STATUS_FILE = REPO_TRANSMUTE / "data" / "_repo_index_status.json"


def main():
    cmd = [
        sys.executable, "-m", "repo_transmute.cli",
        "index",
        "--blueprints-dir", str(REPO_TRANSMUTE / "data" / "blueprints"),
        "--index-dir", str(REPO_TRANSMUTE / "data" / "txtai"),
    ]

    result = subprocess.run(
        cmd,
        cwd=REPO_TRANSMUTE,
        capture_output=True,
        text=True,
        timeout=600,
    )

    output = result.stdout + result.stderr

    # Parse output for meaningful stats
    # e.g. "Indexed 0 documents (0 functions, 0 classes)"
    #      "Skipped 11 unchanged repo(s)"
    #      "Total repos in index: 11"
    doc_count = 0
    repos_in_index = 0
    repos_skipped = 0

    for line in output.splitlines():
        m = re.search(r"Indexed (\d+) documents", line)
        if m:
            doc_count = int(m.group(1))
        m = re.search(r"Total repos in index:\s*(\d+)", line)
        if m:
            repos_in_index = int(m.group(1))
        m = re.search(r"Skipped (\d+) unchanged repo", line)
        if m:
            repos_skipped = int(m.group(1))

    data = {
        "status": "OK" if result.returncode == 0 else "FAILED",
        "returncode": result.returncode,
        "new_docs_indexed": doc_count,
        "repos_in_index": repos_in_index,
        "repos_skipped": repos_skipped,
        "stdout_tail": result.stdout[-1000:] if result.stdout else "",
        "stderr_tail": result.stderr[-1000:] if result.stderr else "",
    }

    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_FILE, "w") as f:
        json.dump(data, f, indent=2)

    if result.returncode == 0:
        print(f"INDEX_OK|{repos_in_index}repos {doc_count}new")
    else:
        print(f"INDEX_FAILED")
        print(result.stderr[-500:])

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
