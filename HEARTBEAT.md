# Night Owl — RepoTransmute

**Last updated:** 2026-04-11T04:11 UTC (Saturday night)
**Agent:** Night Owl (zoul)
**Session:** cron:74e1c3a5-ea20-471f-99d9-b830350fa24e

## Current Status

RepoTransmute is in active development. All 539 tests pass. Night Owl is initialized and running.

## Priority Stack (from ROADMAP.md)

### HIGH Priority

1. **Fix chunked processing (process ALL chunks)**
   - The `_topological_sort` in `Reassembler` only considers chunks in `transpiled.keys()` when computing order. If a chunk fails, `combine()` may produce incomplete output.
   - `transpile_all_chunks` loop iterates ALL `chunk_order` chunks correctly (exception handling with `continue`).
   - Root issue: `combine()` uses `_topological_sort()` which filters to `transpiled.keys()`. A failed chunk is not in `transpiled` so `combine()` never includes it.
   - Also: dependency detection in `create_chunks` uses `j < i` constraint and doesn't detect cross-chunk imports when Python import `from mod0 import helper` has module prefix (stored as `mod0.helper`) vs export `helper` — no match.
   - **Status: Needs deeper investigation + fix**

2. **Add runtime test execution**
   - `run_tests()` is wired into pipeline as Step 6.
   - Need to verify it works end-to-end with real test commands for each language.
   - **Status: Partially done, needs verification**

### MEDIUM Priority

3. **Preserve directory structure in output**
   - Currently `write_files()` may flatten output. Needs to preserve source tree structure.
   - **Status: Not started**

4. **Cross-chunk context**
   - Pass context from previously transpiled chunks to the LLM for better cross-chunk references.
   - **Status: Not started**

## Go Support Status

✅ **Scaffold complete.** All 57 Go parser tests passing.

### Remaining Go Issues (from GO_SUPPORT_HANDOFF.md)

- **Issue 1 (DUPLICATE NAMES):** `extract_from_go()` correctly skips methods via `is_method` check. Test `test_preserves_both_top_level_and_method_with_same_name` tests the INTERNAL function `_extract_go_function_bodies`, not `extract_from_go`. This may be a documentation mismatch — actual behavior is correct.
- **Issue 2 (EMBEDDED INTERFACE `_` NAMES):** ✅ **FIXED 2026-04-11.** `ReadWriter` now correctly shows `Read` and `Write` methods from embedded `Reader`/`Writer`. The goast binary was rebuilt.
- **Issue 3 (REGEX FALLBACK STUB):** `_extract_from_go_regex()` returns empty structs/interfaces. Graceful degradation works (falls back to empty). Could be improved but is low priority.

## What's Been Done

- 2026-04-11: Fixed embedded interface extraction bug in `scripts/goast/main.go`. Added `collectInterfaceTypes()` and `extractMethodsFromInterface()` functions to properly resolve embedded interface references (e.g., `type ReadWriter interface { Reader Writer }`). Rebuilt `goast` binary. All 57 Go tests + 539 total tests pass.
- 2026-04-11: Initialized Night Owl heartbeat and memory files.

## Notes

- The `chunk_order` in `transpile_all_chunks` is pre-computed before any transpiling, so the loop iterates ALL chunks even if dependencies aren't tracked.
- The goast binary lives at `scripts/goast/goast` and is built with `CGO_ENABLED=0 go build`.
- Full test suite: `python3 -m pytest tests/ -q` → 539 passed, 8 skipped.
