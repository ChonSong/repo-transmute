#!/usr/bin/env python3
"""
post_observability.py — generate and post RepoTransmute observability summary to Discord.

Reads status files written by prior lobster steps:
  data/_repo_stale_status.json
  data/_repo_reingest_status.json
  data/_repo_index_status.json
  data/_repo_transpile_status.json

Posts a formatted summary to Discord #night-owl-reports channel (or #evaluator-alerts).
Always fires — even on CLEAN — as this is the observability step.
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_TRANSMUTE = Path(__file__).parent.parent
DATA_DIR = REPO_TRANSMUTE / "data"

DISCORD_CHANNEL = "night-owl-reports"
STATUS_FILES = {
    "stale": DATA_DIR / "_repo_stale_status.json",
    "reingest": DATA_DIR / "_repo_reingest_status.json",
    "index": DATA_DIR / "_repo_index_status.json",
    "transpile": DATA_DIR / "_repo_transpile_status.json",
}


def load_json(path: Path) -> dict:
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


def format_time():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def build_summary():
    stale = load_json(STATUS_FILES["stale"])
    reingest = load_json(STATUS_FILES["reingest"])
    index = load_json(STATUS_FILES["index"])
    transpile = load_json(STATUS_FILES["transpile"])

    lines = [
        f"**RepoTransmute Heartbeat** `{format_time()}`",
        "",
    ]

    # Stale repos
    stale_repos = stale.get("stale_repos", [])
    if stale_repos:
        lines.append(f"**⚠️ {len(stale_repos)} stale repos detected**")
        for r in stale_repos[:5]:
            lines.append(f"  • `{r['repo']}` (remote: {r['remote_head'][:10]})")
        if len(stale_repos) > 5:
            lines.append(f"  … and {len(stale_repos) - 5} more")
    else:
        lines.append("✅ All repos up-to-date (no stale)")

    # Reingest
    reingests = reingest.get("reingests", [])
    if reingests:
        ok = sum(1 for r in reingests if r.get("success"))
        lines.append(f"🔄 Re-ingested {ok}/{len(reingests)} stale repos")
    elif reingest.get("status") == "SKIP":
        lines.append("🔄 No re-ingest needed")
    elif reingest.get("status") == "DONE":
        lines.append("🔄 Re-ingest complete")

    # Index
    idx = index.get("status", "UNKNOWN")
    repos_in_index = index.get("repos_in_index", "?")
    new_docs = index.get("new_docs_indexed", 0)
    if idx == "OK":
        lines.append(f"✅ TXTAI index: {repos_in_index} repos indexed ({new_docs} new docs)")
    else:
        lines.append(f"❌ TXTAI index: {idx}")

    # Transpile sample
    trans = transpile.get("status", "UNKNOWN")
    if transpile.get("transpiles"):
        ok = sum(1 for r in transpile["transpiles"] if r.get("validation_ok"))
        total = len(transpile["transpiles"])
        if trans == "TRANSPILE_OK":
            lines.append(f"✅ Transpile sample: {ok}/{total} chunks valid")
        else:
            lines.append(f"❌ Transpile sample: {ok}/{total} chunks valid")
    elif trans == "SKIP":
        lines.append("⏭️ No transpile sample run")
    elif trans == "UNKNOWN":
        pass  # Not run yet

    lines.append("")
    lines.append(f"_RepoTransmute heartbeat_")

    return "\n".join(lines)


def post_to_discord(message: str):
    """Post message to Discord channel via openclaw message tool."""
    cmd = [
        "openclaw", "message",
        "--channel", DISCORD_CHANNEL,
        "--text", message,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception as e:
        print(f"Discord post failed: {e}", file=sys.stderr)
        return False


def main():
    summary = build_summary()
    print(summary)
    print()

    posted = post_to_discord(summary)
    if posted:
        print(f"Posted to Discord #{DISCORD_CHANNEL}")
    else:
        print(f"Could not post to Discord (openclaw message may require interactive approve)")

    # Always exit 0 — observability step should never halt the workflow
    return 0


if __name__ == "__main__":
    sys.exit(main())
