# HEARTBEAT.md — RepoTransmute / Zoul Night Owl

## System Status

- **TXTAI Index**: ✅ Built (12,181 docs, 11 repos)
- **Pipeline**: ✅ Working (652 tests pass)
- **Nightly cron**: ✅ Active (runs ~6:30 UTC each night)

## No active priorities — awaiting Sean direction

The system is in good working order. All phases are complete.

## Recent Work

- **2026-04-22 Night Owl**: Documentation update — ROADMAP.md refreshed to reflect current system status (all phases 1-8 complete). Multi-language support (Python, JS/TS, Rust, Go) and runtime test execution confirmed working. System verification complete — all 652 tests pass.

- **2026-04-19 Night Owl**: Reassembler `write_files()` improvements:
  1. **file_ext propagation through `combine()`**: `_build_per_file_units()` was defaulting to `.ts` for any unrecognized source extension (Go `.go`, Rust `.rs`), so Go→Rust produced `math.ts` instead of `math.rs`. Now `combine(file_ext)` passes the target extension down so correct extensions are used throughout.
  2. **`src_dir` parameter for `write_files()`**: Allows redirecting bare-filename output (e.g. `math.rs`) into a subdirectory (e.g. `src/math.rs`) — critical for Rust/cargo projects that require output under `src/`. Previously required manual file moving after `write_files()` returned.
  - Updated `test_pipeline_rust_with_cargo_test_e2e` to use `src_dir="src"` instead of manual post-processing.
  - 652 tests pass. Commit `11940f6`.

- **2026-04-19 Night Owl**: End-to-end test execution — `run_tests()` now verified with real Vitest (JS/TS) and Cargo test runners. Fixed Vitest v4 output parsing (`Tests  N passed` format). Fixed JS test string formatting (Python `.format()` brace escaping). Fixed pipeline Rust test path (`file_ext="rs"` → `[[bin]]` target). Added 8 new e2e tests (3 JS/Vitest + 3 Rust/Cargo + 2 pipeline). 652 total tests pass. (Commit `2e3f8a1`)

- **2026-04-14 Night Owl**: Multi-language chunker — Go, JS/TS, Rust support. Fixed CLI/coordinator bug (always defaulting to Python). Rust/Go dependency parsing (Cargo.toml, go.mod). 62 new tests. (Commits `7cb0729`, `9e7a901`)

- **2026-04-12 Night Owl**: Cross-chunk context (LLM sees prior exports) + Go AST-aware test generation. 15 new tests.

- **2026-04-11 Night Owl**: Fixed cross-chunk dependency detection. ClawFlow orchestration (Phase 7).

## Phase 8 — TXTAI Hybrid Search (DONE)

Implemented as `TxtaiClient.hybrid_search()` + `BlueprintSearch.hybrid_search()`:
- BM25 keyword scoring via `_bm25_score()` — pure Python, reads from SQLite sidecar
- Semantic vector search via txtai embeddings
- Min-max normalisation + weighted sum fusion
- Configurable `semantic_weight` (default 0.7) / `keyword_weight` (default 0.3)

## Phase 7 — ClawFlow Orchestration (DONE 2026-04-11)

Lobster workflow at `scripts/flows/repo_transmute_heartbeat.lobster`.

## Next Possible Directions (when Sean provides direction)

1. **Performance optimization** - Large file processing could be optimized
2. **Additional language support** - Java, Ruby, PHP
3. **Enhanced error reporting** - Better diagnostics for transpilation failures
4. **UI/UX improvements** - Better CLI output, progress indicators
5. **Integration testing** - More complex real-world repository tests