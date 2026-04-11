# HEARTBEAT.md — RepoTransmute / Zoul Night Owl

## System Status

- **TXTAI Index**: ✅ Built (12,181 docs, 11 repos)
- **Pipeline**: ✅ Working (541 tests pass)
- **Nightly cron**: ✅ Active (runs ~6:30 UTC each night)

## No active priorities — awaiting Sean direction

The system is in good working order. All phases are complete.

## Recent Work

- **2026-04-11 (Night Owl)**: ClawFlow orchestration — RepoTransmute heartbeat lobster workflow implemented (Phase 7 complete)

- **2026-04-11 (Night Owl)**: Fixed `status` command to detect txtai 6.x index via `config.json` instead of `index.faiss`. Also added `TestStatusCommand` test. (Commit `69aefd9`)

- **2026-04-11**: TXTAI hybrid search — Phase 8 complete

- **2026-04-10 (evening)**: Fixed TXTAI `repos()`, `languages()`, `stats()`, and `cross_repo_patterns()` to use reliable batch metadata lookup instead of `search("*")` wildcard

- **2026-04-10**: Fixed `Reassembler.combine()` and `_split_into_file_units()` directory-structure bug (Night Owl session)

- **2026-04-08**: TXTAI index rebuilt, `notebook diff` CLI added

## Phase 8 — TXTAI Hybrid Search (DONE)

Implemented as `TxtaiClient.hybrid_search()` + `BlueprintSearch.hybrid_search()`:

- **BM25 keyword scoring** via `_bm25_score()` — pure Python, reads text from SQLite sidecar
- **Semantic vector search** via existing txtai embeddings
- **Min-max normalisation** of both score components before fusion
- **Weighted sum** with configurable `semantic_weight` (default 0.7) / `keyword_weight` (default 0.3)
- `semantic_limit=100` to get more candidates than final limit (improves keyword recall)
- Result dict carries `semantic_score` and `keyword_score` alongside fused `score`

High-level API (`BlueprintSearch`):
- `search(query, hybrid=True)` — shortcut flag
- `hybrid_search(query, limit=10, semantic_weight=0.7, keyword_weight=0.3)` — explicit weights
- `SearchHit.semantic_score` / `.keyword_score` attributes
- `SearchResults.is_hybrid` flag (propagated through filter methods)

## Phase 7 — ClawFlow Orchestration (DONE 2026-04-11)

Lobster workflow at `scripts/flows/repo_transmute_heartbeat.lobster`:

```
detect_stale (git remote HEAD vs local HEAD for each cached repo)
  → reingest_stale (repo-transmute ingest for stale repos)
    → run_index (TXTAI indexer, incremental)
      → transpile_sample (transpile chunk 0 to validate pipeline)
        → observability_report (post summary to Discord #night-owl-reports)
```

Supporting scripts in `scripts/`:
- `check_repos_stale.py` — detect stale cached repos
- `reingest_stale_repos.py` — re-ingest stale repos
- `run_index.py` — run TXTAI indexer
- `transpile_sample.py` — validate pipeline via sample transpile
- `post_observability.py` — Discord observability summary

## Phase 6 — Runtime Validation

- [x] TXTAI index rebuilt (done)
- [x] Discord alert step in lobster workflow — alert_and_halt sends to `#evaluator-alerts` when critical drift or critical oracle failure detected (in agent-interaction-evaluator-repo)
- [x] ClawFlow orchestration (Phase 7 — done 2026-04-11)
