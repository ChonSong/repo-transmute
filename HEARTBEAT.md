# HEARTBEAT.md — RepoTransmute / Zoul Night Owl

## System Status

- **TXTAI Index**: ✅ Built (12,181 docs, 11 repos)
- **Pipeline**: ✅ Working (558 tests pass)
- **Nightly cron**: ✅ Active (runs ~6:30 UTC each night)

## No active priorities — awaiting Sean direction

The system is in good working order. All phases are complete.

## Recent Work

- **2026-04-12 Night Owl**: Implemented cross-chunk context — LLM now sees exports from prior chunks when transpiling (commit `78df5b7`). When transpiling chunk N, the pipeline accumulates exports from chunks 0..N-1 and embeds them in the prompt, enabling correct import generation and preventing duplicate definitions. 11 new tests.

- **2026-04-12 Night Owl**: Integrated `go_test_gen.py` AST-aware test generation into pipeline coordinator (commit `beb8c54`). Replaced basic regex-based Go test generation with proper AST parsing. Falls back to regex on parse errors. 4 new tests.

- **2026-04-11 Night Owl**: Fixed cross-chunk dependency detection in `create_chunks()` (commit `f64aa89`). Imports were stored as qualified dotted paths (`pkg.mod.Symbol`) while exports are bare names (`Symbol`), so the direct membership check never matched. Added `_symbol_from_qualified_import()` helper that strips the leading prefix and filters stdlib imports. 543 tests pass (up from 541).

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

Lobster workflow at `scripts/flows/repo_transmute_heartbeat.lobster`.

## Cross-Chunk Context Feature (2026-04-12)

When transpiling chunk N, the LLM now receives context about symbols exported by previously-transpiled chunks (0..N-1). This includes:
- Output file paths for each exported symbol
- Function names and signatures
- Data structure names, types, and fields
- Language-specific import examples

The context is accumulated progressively: after each chunk is transpiled, `_build_chunk_export_info()` extracts its exports and appends them to the running list. Subsequent chunks receive the full accumulated context via `cross_chunk_exports` parameter in `transpile_chunk()`.

Flow: `coordinator.transpile_all_chunks()` → accumulates `cross_chunk_exports_acc` → passes to `transpile_chunk()` → embeds in `blueprint_data["blueprint"]["cross_chunk_exports"]` → serialized to YAML → `Transpiler.transpile()` → `build_transpile_prompt(blueprint, ..., cross_chunk_exports=...)` → `format_cross_chunk_context()` → rendered as "# CROSS-CHUNK CONTEXT" section in prompt.

## Go Test Generation Integration (2026-04-12)

The `_generate_go_tests()` function now uses the AST-aware `go_test_gen` module instead of basic regex. Benefits:
- Proper parameter extraction with type info
- Return type awareness (error checks, value comparisons)
- Fallback to regex for malformed Go source
- Method test stubs via separate `generate_test_file_for_methods()`

## Open Items

1. **Runtime test execution**: `run_tests()` is implemented and has unit tests, but has not been verified end-to-end with a real transpiled project
2. **Directory structure preservation**: Output directory structure in `write_files()` uses the `// filename:` marker paths; if LLM generates incorrect paths, structure could be wrong
3. ~~**Cross-chunk context**: LLM gets no context about what other chunks exported when transpiling a chunk~~ → **DONE 2026-04-12**
4. ~~**Go test generation**: `go_test_gen.py` exists but has not been integrated into the pipeline coordinator~~ → **DONE 2026-04-12**
