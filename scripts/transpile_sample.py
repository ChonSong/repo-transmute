#!/usr/bin/env python3
"""
transpile_sample.py — transpile sample chunks to validate pipeline health.

Selects a cached Python repo, transpiles chunk 0, and checks if validation passes.
Writes results to data/_repo_transpile_status.json.
Always exits 0 — failures are reported via status file.
"""
import subprocess
import sys
import json
import random
from pathlib import Path

REPO_TRANSMUTE = Path(__file__).parent.parent
CACHE_DIR = REPO_TRANSMUTE / "data" / "cache"
STATUS_FILE = REPO_TRANSMUTE / "data" / "_repo_transpile_status.json"


def get_python_cached_repos():
    """Return list of cached repos that have Python source files (can be transpiled)."""
    if not CACHE_DIR.exists():
        return []
    result = []
    for p in CACHE_DIR.iterdir():
        if not (p.is_dir() and "__" in p.name):
            continue
        py_files = list(p.rglob("*.py"))
        if py_files:
            result.append(p.name)
    return result


def transpile_chunk(repo: str, chunk_id: int, timeout: int = 300) -> dict:
    """Transpile a single chunk using repo-transmute transpile --repo X --chunk-id Y."""
    cmd = [
        sys.executable, "-m", "repo_transmute.cli",
        "transpile",
        "--repo", repo,
        "--chunk-id", str(chunk_id),
        "--cache-dir", str(CACHE_DIR),
        "--target", "typescript",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_TRANSMUTE,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr

        # Check for error conditions
        if result.returncode != 0:
            return {
                "repo": repo,
                "chunk_id": chunk_id,
                "success": False,
                "validation_ok": False,
                "error": "exit_nonzero",
                "output_tail": output[-500:],
            }

        if "Output was emptied by cleaning" in output:
            return {
                "repo": repo,
                "chunk_id": chunk_id,
                "success": False,
                "validation_ok": False,
                "error": "llm_output_emptied",
                "output_tail": output[-500:],
            }

        # Check for timeouts
        if "timed out" in output:
            return {
                "repo": repo,
                "chunk_id": chunk_id,
                "success": False,
                "validation_ok": False,
                "error": "timeout",
                "output_tail": output[-500:],
            }

        # Parse ValidationResult from the output
        validation_ok = "✓ Validation passed" in output

        return {
            "repo": repo,
            "chunk_id": chunk_id,
            "success": True,
            "validation_ok": validation_ok,
            "output_tail": output[-500:],
        }
    except subprocess.TimeoutExpired:
        return {
            "repo": repo,
            "chunk_id": chunk_id,
            "success": False,
            "validation_ok": False,
            "error": "timeout",
        }
    except Exception as e:
        return {
            "repo": repo,
            "chunk_id": chunk_id,
            "success": False,
            "validation_ok": False,
            "error": str(e),
        }


def main():
    repos = get_python_cached_repos()
    if not repos:
        print("TRANSPILE_SKIP|0  (no cached Python repos)")
        _write_status("SKIP", [])
        return 0

    # Try up to 3 repos until we get a successful validation
    shuffled = random.sample(repos, min(len(repos), 5))
    results = []

    for repo in shuffled:
        if len([r for r in results if r.get("validation_ok")]) >= 1:
            break  # Got at least one successful validation
        if len(results) >= 3:
            break  # Tried enough

        print(f"Trying {repo} (chunk 0)...")
        r = transpile_chunk(repo, 0)
        results.append(r)
        icon = "✓" if r["validation_ok"] else "✗"
        reason = r.get("error", "OK" if r["validation_ok"] else "validation_fail")
        print(f"  {icon} {repo} chunk0: {reason}")

    ok_count = sum(1 for r in results if r["validation_ok"])
    total = len(results)
    status = "TRANSPILE_OK" if ok_count > 0 else "TRANSPILE_ALL_FAILED"
    _write_status(status, results)
    print(f"{status}|{ok_count}/{total}")
    return 0  # Always exit 0 — report via status file


def _write_status(status: str, results: list):
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_FILE, "w") as f:
        json.dump({"status": status, "transpiles": results}, f, indent=2)


if __name__ == "__main__":
    sys.exit(main())
