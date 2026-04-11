name: repo_transmute_heartbeat
description: "Nightly RepoTransmute pipeline — detect stale repos, re-ingest, re-index, validate transpilation, post observability report"

steps:

  # ── Step 1: DETECT STALE REPOS ─────────────────────────────
  # Check git remote HEAD vs local HEAD for each cached repo.
  # Output: STALE|<count> or CLEAN|0 → data/_repo_stale_status.json
  - id: detect_stale
    run: python3 /home/osboxes/.openclaw/workspace/zoul/repo-transmute/scripts/check_repos_stale.py
    stdin: null

  # ── Step 2: RE-INGEST STALE REPOS ─────────────────────────
  # Re-ingest any repos flagged stale by step 1.
  # Reads: data/_repo_stale_status.json
  # Output: REINGEST_DONE|<n> or REINGEST_SKIP|0 → data/_repo_reingest_status.json
  - id: reingest_stale
    run: python3 /home/osboxes/.openclaw/workspace/zoul/repo-transmute/scripts/reingest_stale_repos.py
    stdin: null

  # ── Step 3: RUN TXTAI INDEXER ──────────────────────────────
  # Run the indexer (skip_unchanged=True means unchanged repos are cheap).
  # Output: INDEX_OK|<doc_count> → data/_repo_index_status.json
  - id: run_index
    run: python3 /home/osboxes/.openclaw/workspace/zoul/repo-transmute/scripts/run_index.py
    stdin: null

  # ── Step 4: TRANSPILE SAMPLE VALIDATION ───────────────────
  # Transpile 3 sample chunks to validate the pipeline end-to-end.
  # Output: TRANSPILE_OK|<n> or TRANSPILE_ALL_FAILED → data/_repo_transpile_status.json
  - id: transpile_sample
    run: python3 /home/osboxes/.openclaw/workspace/zoul/repo-transmute/scripts/transpile_sample.py
    stdin: null

  # ── Step 5: OBSERVABILITY REPORT ──────────────────────────
  # Always fires. Posts summary to Discord #night-owl-reports.
  - id: observability_report
    run: python3 /home/osboxes/.openclaw/workspace/zoul/repo-transmute/scripts/post_observability.py
    stdin: null
