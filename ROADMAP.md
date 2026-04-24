# RepoTransmute Roadmap

> Last Updated: 2026-04-22  
> Review Frequency: Weekly (via heartbeat)

## Vision

AI-powered code transpilation engine that:
1. Ingests repositories (clone + analyze)
2. Validates compatibility (source → target routing)
3. Generates language-agnostic blueprints with full function bodies
4. Transpiles to target languages (with multi-agent review)
5. Validates output compiles and runs
6. Provides semantic search (txtai)
7. Unifies frontends via screenshot reconstruction

---

## Current Status Summary (2026-04-22)

**System Fully Operational:** All 652 tests pass (8 skipped due to missing API keys). Multi-language support for Python, TypeScript/JavaScript, Rust, and Go is working. Runtime test execution verified with real Vitest (JS/TS), Cargo (Rust), pytest (Python), and go test (Go). Cross-chunk context implemented. Directory structure preserved via `src_dir` parameter in Reassembler.

---

## Phases

### Phase 1: MVP ✅ COMPLETED
**Goal:** End-to-end proof of concept — clone a repo, extract blueprint, save YAML

| Task | Status | Notes |
|------|--------|-------|
| Project setup | ✅ | pyproject.toml, structure |
| Clone service | ✅ | gh CLI integration |
| Language detection | ✅ | Extension + package manager heuristics |
| File walker | ✅ | Ignore patterns, recursive |
| Blueprint extraction | ✅ | Functions + classes + bodies |
| Blueprint storage | ✅ | YAML output with full bodies |
| CLI interface | ✅ | `ingest`, `status` commands |

---

### Phase 2: LLM Transpilation ✅ COMPLETED
**Goal:** Connect LLM to convert blueprints to target languages

| Task | Status | Notes |
|------|--------|-------|
| txtai install | ✅ | v9.7.0 installed |
| Prompt templates | ✅ | JS→TS, Python→Python, Python→Rust |
| LLM integration | ✅ | MiniMax-M2.7 via API |
| CLI transpile cmd | ✅ | `repo-transmute transpile` |
| Output cleaning | ✅ | Remove thinking tags |
| Multi-target support | ✅ | TypeScript, Rust, Python |

**Model:** MiniMax-M2.7 (via MiniMax API)

---

### Phase 3: Compatibility & Safety ✅ COMPLETED
**Goal:** Prevent failures with compatibility gates

| Task | Status | Notes |
|------|--------|-------|
| Routing table | ✅ | Source → Target mapping |
| Compatibility checker | ✅ | Confidence scoring |
| Complexity analysis | ✅ | 1-10 score |
| CLI integration | ✅ | Shows warnings before transpile |
| Confidence thresholds | ✅ | ≥80% = go, <50% = skip |

---

### Phase 4: Multi-Agent Quality Pipeline ✅ COMPLETED
**Goal:** Multi-agent review for quality

| Task | Status | Notes |
|------|--------|-------|
| Agent pipeline design | ✅ | CODER → REVIEWER flow |
| Coder agent | ✅ | Extract + transpile |
| Reviewer agent | ✅ | Quality check |
| TDD agent | ✅ | Test generation |
| Security reviewer | ⏳ | Security audit |

---

### Phase 5: Multi-Language Chunked Processing ✅ COMPLETED (2026-04-14)
**Goal:** Handle large repos with proper chunking across multiple languages

| Task | Status | Notes |
|------|--------|-------|
| Parse requirements.txt | ✅ | Python dependency parsing |
| Parse package.json | ✅ | JS/TS dependency parsing |
| Parse Cargo.toml | ✅ | Rust dependency parsing (via Cargo.toml) |
| Parse go.mod | ✅ | Go dependency parsing |
| Dependency classifier | ✅ | External vs internal |
| Queue system | ✅ | SQLite-backed |
| Recursive processing | ✅ | Process deps after main repo |
| **Full repo chunking** | ✅ | Transpiles ALL chunks |
| **Preserve structure** | ✅ | Keep directory layout via `src_dir` parameter |
| Multi-language support | ✅ | Python, JS/TS, Rust, Go |

---

### Phase 6: Runtime Validation ✅ COMPLETED (2026-04-19)
**Goal:** Verify generated code compiles and runs

| Task | Status | Notes |
|------|--------|-------|
| TypeScript validation | ✅ | tsc --noEmit |
| Rust validation | ✅ | cargo check |
| Python validation | ✅ | py_compile |
| Go validation | ✅ | go build |
| **Run tests** | ✅ | Execute test suites (Vitest v4, Cargo, pytest, go test) |
| **Browser validation** | ✅ | Playwright screenshot |
| **Integration tests** | ✅ | 8 new e2e tests added |

---

### Phase 7: Cross-Chunk Context & Go Test Generation ✅ COMPLETED (2026-04-12)
**Goal:** Maintain context across chunks and improve test generation

| Task | Status | Notes |
|------|--------|-------|
| **Cross-chunk context** | ✅ | LLM sees exports from prior chunks |
| **Go test generation** | ✅ | AST-aware test stubs for Go |
| **Go support** | ✅ | Full Go language support (parser, test gen, dependency) |
| Multi-language dependency graph | ✅ | Cross-language dependency tracking |

---

### Phase 8: TXTAI Hybrid Search ✅ COMPLETED (2026-04-08)
**Goal:** Enable semantic search across all blueprints

| Task | Status | Notes |
|------|--------|-------|
| Index blueprints | ✅ | 12,181 docs across 11 repos (rebuilt 2026-04-08) |
| Search API | ✅ | Hybrid search (BM25 + semantic) |
| Cross-repo patterns | ✅ | Natural language queries |
| Notebook storage | ✅ | Document transpilation insights |
| Hybrid search fusion | ✅ | Configurable semantic/keyword weights |

---

### Phase 9: Frontend Unification
**Goal:** Screenshot-based component reconstruction

| Task | Status | Notes |
|------|--------|-------|
| Screenshot capture | ✅ | Playwright |
| Vision analysis | ⏳ | LLM vision → component spec |
| Component blueprint | ⏳ | Layout + interactions |
| TypeScript generator | ⏳ | Generate .ts files |

---

## Next Possible Directions (when Sean provides direction)

1. **Performance optimization** - Large file processing could be optimized
2. **Additional language support** - Java, Ruby, PHP, C#  
3. **Enhanced error reporting** - Better diagnostics for transpilation failures
4. **UI/UX improvements** - Better CLI output, progress indicators
5. **Integration testing** - More complex real-world repository tests
6. **Cloud deployment** - Scale to handle larger repositories
7. **Batch processing** - Process multiple repositories in parallel

---

## Testing Results

> Last updated: 2026-04-22

| Repo | Source | Target | Functions | Output | Status |
|------|--------|--------|-----------|--------|--------|
| lfnovo/open-notebook | TypeScript | TypeScript | 10k+ | 257 lines | ⚠️ Partial |
| HKUDS/nanobot | Python | TypeScript | 987 | 1,033 lines | ✅ |
| lucmuss/nanobot-webgui | Python | TypeScript | 694 | 379 lines | ✅ |
| shadcn-ui/next-template | TypeScript | TypeScript | 20 | 12k lines | ✅ |

**Test Suite Status:** 652 tests pass, 8 skipped (multi-language chunking, runtime e2e tests all pass)

---

## Open Questions

1. **Performance scaling:** How to handle repositories with 10k+ functions?
2. **Model choice:** Should we support multiple LLM backends?
3. **Quality metrics:** How to measure transpilation quality beyond test passing?
4. **User feedback:** How to incorporate user corrections back into the system?

---

## Heartbeat Review Checklist

When reviewing this roadmap during heartbeat:

- [ ] Review completed tasks from last week
- [ ] Move completed items to Phase N ✅ status
- [ ] Identify blockers for in-progress items
- [ ] Add any new tasks that emerged
- [ ] Update "Next Actions" based on current priorities
- [ ] Check if open questions can be answered

---

*This roadmap is a living document. Update it during heartbeat reviews.*