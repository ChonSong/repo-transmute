# RepoTransmute Roadmap

> Last Updated: 2026-03-23
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

## Current Limitations (To Fix)

| # | Limitation | Impact | Priority |
|---|------------|--------|----------|
| 1 | **No Go support** | Can't process Go repos | HIGH |
| 2 | **Token limits** | Large repos truncate (~30 functions per pass) | HIGH |
| 3 | **No chunked processing** | Only first chunk gets transpiled | HIGH |
| 4 | **Single file output** | Doesn't preserve directory structure | MEDIUM |
| 5 | **No runtime validation** | Can't verify code runs | HIGH |
| 6 | **No context between chunks** | Loses cross-file relationships | MEDIUM |

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

### Phase 5: Chunked Processing 🔄 IN PROGRESS
**Goal:** Handle large repos with proper chunking

| Task | Status | Notes |
|------|--------|-------|
| Parse requirements.txt | ✅ | |
| Parse package.json | ✅ | |
| Parse Cargo.toml | ⏳ | |
| Dependency classifier | ✅ | External vs internal |
| Queue system | ✅ | SQLite-backed |
| Recursive processing | ⏳ | Process deps after main repo |
| **Full repo chunking** | 🔄 | Must transpile ALL chunks |
| **Preserve structure** | 🔄 | Keep directory layout |

---

### Phase 6: Runtime Validation 🔄 IN PROGRESS
**Goal:** Verify generated code compiles and runs

| Task | Status | Notes |
|------|--------|-------|
| TypeScript validation | ✅ | tsc --noEmit |
| Rust validation | ✅ | cargo check |
| Python validation | ✅ | py_compile |
| **Run tests** | 🔄 | Execute test suites |
| **Browser validation** | ✅ | Playwright screenshot |
| **Integration tests** | ⏳ | Full app testing |

---

### Phase 7: Language Support Expansion
**Goal:** Support more languages

| Task | Status | Notes |
|------|--------|-------|
| **Go support** | 🟡 Scaffolded (57 tests, goast binary) | Go AST parser via goast binary, regex fallback |
| Java support | ⏳ | |
| Ruby support | ⏳ | |
| PHP support | ⏳ | |

---

### Phase 8: TXTAI Semantic Layer
**Goal:** Enable semantic search across all blueprints

| Task | Status | Notes |
|------|--------|-------|
| Index blueprints | ⏳ | Embeddings |
| Search API | ⏳ | Natural language queries |
| Cross-repo patterns | ⏳ | "Find similar auth patterns" |
| Notebook storage | ⏳ | Document transpilation insights |

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

## Next Actions (Priority Order)

1. [ ] **HIGH** - Fix chunked processing (process ALL chunks)
2. [ ] **HIGH** - Add Go language support
3. [ ] **HIGH** - Add runtime test execution
4. [ ] **MEDIUM** - Preserve directory structure in output
5. [ ] **MEDIUM** - Add cross-chunk context
6. [ ] **LOW** - More language parsers

---

## Testing Results

> Last updated: 2026-04-12

| Repo | Source | Target | Functions | Output | Status |
|------|--------|--------|-----------|--------|--------|
| lfnovo/open-notebook | TypeScript | TypeScript | 10k+ | 257 lines | ⚠️ Partial |
| HKUDS/nanobot | Python | TypeScript | 987 | 1,033 lines | ✅ |
| lucmuss/nanobot-webgui | Python | TypeScript | 694 | 379 lines | ✅ |
| shadcn-ui/next-template | TypeScript | TypeScript | 20 | 12k lines | ✅ |

---

## Open Questions

1. **Chunk strategy:** Process sequentially or parallel?
2. **Output format:** Single file or directory structure?
3. **Validation:** How to handle test failures?

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
