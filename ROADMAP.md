# RepoTransmute Roadmap

> Last Updated: 2026-03-20
> Review Frequency: Weekly (via heartbeat)

## Vision

AI-powered code transpilation engine that:
1. Ingests repositories (clone + analyze)
2. Validates compatibility (source → target routing)
3. Generates language-agnostic blueprints
4. Transpiles to target languages (with multi-agent review)
5. Provides semantic search (txtai)
6. Unifies frontends via screenshot reconstruction

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
| Blueprint extraction | ✅ | Functions + classes |
| Blueprint storage | ✅ | YAML output |
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

**Routing Table:**
| Source | Target | Confidence |
|--------|--------|------------|
| JavaScript | TypeScript | 95% |
| TypeScript | TypeScript | 98% |
| Python | Python | 90% |
| Go | Go | 85% |
| Rust | (keep) | - |
| Unknown | Skip | 0% |

---

### Phase 4: Multi-Agent Quality Pipeline 🔄 IN PROGRESS
**Goal:** Multi-agent review for quality

| Task | Status | Notes |
|------|--------|-------|
| Agent pipeline design | ✅ | CODER → REVIEWER flow |
| Coder agent | ✅ | Extract + transpile |
| Reviewer agent | ✅ | Quality check |
| TDD agent | ⏳ | Test generation |
| Security reviewer | ⏳ | Security audit |

---

### Phase 5: Dependency Resolution
**Goal:** Recursively handle external/internal dependencies

| Task | Status | Notes |
|------|--------|-------|
| Parse requirements.txt | ⏳ | |
| Parse package.json | ⏳ | |
| Parse Cargo.toml | ⏳ | |
| Dependency classifier | ⏳ | External vs internal |
| Queue system | ⏳ | SQLite-backed |
| Recursive processing | ⏳ | Process deps after main repo |

---

### Phase 6: TXTAI Semantic Layer
**Goal:** Enable semantic search across all blueprints

| Task | Status | Notes |
|------|--------|-------|
| Index blueprints | ⏳ | Embeddings |
| Search API | ⏳ | Natural language queries |
| Cross-repo patterns | ⏳ | "Find similar auth patterns" |
| Notebook storage | ⏳ | Document transpilation insights |

---

### Phase 7: Frontend Unification
**Goal:** Screenshot-based component reconstruction

| Task | Status | Notes |
|------|--------|-------|
| Screenshot capture | ⏳ | Playwright |
| Vision analysis | ⏳ | LLM vision → component spec |
| Component blueprint | ⏳ | Layout + interactions |
| TypeScript generator | ⏳ | Generate .ts files |

---

## Testing Results

| Repo | Source | Target | Confidence | Output | Status |
|------|--------|--------|------------|--------|--------|
| mluberry/nextjs-express | JavaScript | TypeScript | 95% | 33,344 lines | ✅ |
| shadcn-ui/next-template | TypeScript | TypeScript | 98% | 12,487 lines | ✅ |
| MunGell/awesome-for-beginners | Python | Python | 90% | - | ✅ |
| minimaxir/big-list-of-naughty-strings | Go | Go | 85% | - | ✅ |

---

## Quick Wins (Backlog)

- [ ] Add more language parsers (Java, Ruby)
- [ ] Fill handler stubs
- [ ] Add TypeScript validation (tsc --noEmit)
- [ ] Add Rust validation (cargo check)
- [ ] Set up TDD agent for tests
- [ ] Add security reviewer agent

---

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-20 | Python backend | Simplifies AI/ML integration, txtai, tree-sitter |
| 2026-03-20 | MiniMax-M2.7 for transpilation | Available on subscription, strong code gen |
| 2026-03-20 | TypeScript as primary target | Most repos are JS/TS, safer conversion |
| 2026-03-20 | Compatibility gates | Prevent failures, route to best target |
| 2026-03-20 | Multi-agent pipeline | CODER → REVIEWER for quality |

---

## Open Questions

1. **Validation:** Add cargo check for Rust, tsc for TypeScript?
2. **Multi-agent:** Add TDD + Security agents?
3. **Dependency:** Start Phase 5 or finish Phase 4 first?

---

## Next Actions

1. [ ] **HIGH** - Add TypeScript validation (tsc)
2. [ ] **HIGH** - Add Rust validation (cargo check)
3. [ ] **MEDIUM** - Set up TDD agent
4. [ ] **MEDIUM** - Test more repos
5. [ ] **LOW** - Add more language parsers

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
