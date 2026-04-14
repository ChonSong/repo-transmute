# HEARTBEAT.md — RepoTransmute / Zoul Night Owl

## System Status

- **TXTAI Index**: ✅ Built (12,181 docs, 11 repos)
- **Pipeline**: ✅ Working (620 tests pass)
- **Nightly cron**: ✅ Active (runs ~6:30 UTC each night)

## No active priorities — awaiting Sean direction

The system is in good working order. All phases are complete.

## Recent Work

- **2026-04-14 Night Owl**: Multi-language chunker — Go, JS/TS, Rust support in `chunk_repository()`, `create_chunks()`, `count_functions()`, `extract_imports()`, `extract_exports()`. Fixed bug where CLI and coordinator always defaulted to Python. Added TypeScript interface/type export detection. 42 new tests. Also: Rust dependency parsing — `parse_cargo_toml()`, `parse_go_mod()`, `_parse_rust_use()`, Rust dispatch in `parse_imports()`. 20 new tests. (Commits `7cb0729`, `9e7a901`)

- **2026-04-12 Night Owl**: Implemented cross-chunk context — LLM now sees exports from prior chunks when transpiling (commit `78df5b7`). When transpiling chunk N, the pipeline accumulates exports from chunks 0..N-1 and embeds them in the prompt, enabling correct import generation and preventing duplicate definitions. 11 new tests.

- **2026-04-12 Night Owl**: Integrated `go_test_gen.py` AST-aware test generation into pipeline coordinator (commit `beb8c54`). Replaced basic regex-based Go test generation with proper AST parsing. Falls back to regex on parse errors. 4 new tests.

- **2026-04-11 Night Owl**: Fixed cross-chunk dependency detection in `create_chunks()` (commit `f64aa89`). Imports were stored as qualified dotted paths (`pkg.mod.Symbol`) while exports are bare names (`Symbol`), so the direct membership check never matched. Added `_symbol_from_qualified_import()` helper that strips the leading prefix and filters stdlib imports. 543 tests pass (up from 541).

- **2026-04-11 (Night Owl)**: ClawFlow orchestration — RepoTransmute heartbeat lobster workflow implemented (Phase 7 complete)

## Phase 8 — TXTAI Hybrid Search (DONE)

Implemented as `TxtaiClient.hybrid_search()` + `BlueprintSearch.hybrid_search()`:

- **BM25 keyword scoring** via `_bm25_score()` — pure Python, reads text from SQLite sidecar
- **Semantic vector search** via existing txtai embeddings
- **Min-max normalisation** of both score components before fusion
- **Weighted sum** with configurable `semantic_weight` (default 0.7) / `keyword_weight` (default 0.3)
- `semantic_limit=100` to get more candidates than final limit (improves keyword recall)
- Result dict carries `semantic_score` and `keyword_score` alongside fused `score`

## Phase 7 — ClawFlow Orchestration (DONE 2026-04-11)

Lobster workflow at `scripts/flows/repo_transmute_heartbeat.lobster`.

## Multi-Language Chunker Support (2026-04-14)

The chunker now supports Go, JavaScript/TypeScript, and Rust in addition to Python:
- `LANG_EXTENSIONS` mapping and `IGNORE_DIRS` for file discovery
- Language-aware `count_functions()`, `extract_imports()`, `extract_exports()` dispatchers
- `_find_source_files()` with proper filtering (excludes Go test files, hidden dirs, etc.)
- `chunk_repository()` and `create_chunks()` accept `language` parameter
- CLI and coordinator pass detected language through to chunking

## Dependency Parsing (2026-04-14)

- Rust `use` statement parsing with grouped import expansion (`{A, B, C}`)
- `parse_cargo_toml()` for Rust dependency extraction
- `parse_go_mod()` for Go module dependency extraction
- `parse_imports()` dispatches to Rust handler for `.rs` files

## Open Items

1. **Runtime test execution**: `run_tests()` is implemented and has unit tests, but has not been verified end-to-end with a real transpiled project
2. ~~**Cross-chunk context**:~~ → **DONE 2026-04-12**
3. ~~**Go test generation**:~~ → **DONE 2026-04-12**
4. ~~**Multi-language chunker**:~~ → **DONE 2026-04-14**
5. ~~**Cargo.toml/go.mod dependency parsing**:~~ → **DONE 2026-04-14**
