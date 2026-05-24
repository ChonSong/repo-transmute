# RepoTransmute - AI-Powered Code Transpilation Engine

> Automated repository ingestion → compatibility checking → blueprint generation → transpilation

## Vision

AI-powered code transpilation engine that:
1. Ingests repositories (clone + analyze)
2. Validates compatibility (source → target routing)
3. Generates language-agnostic blueprints
4. Transpiles to target languages (with multi-agent review)
5. Provides semantic search (txtai)
6. Unifies frontends via screenshot reconstruction

## Quick Start

```bash
# v2 (recommended) — Vision-driven migration
cd repo-transmute
PYTHONPATH=src python3 -m repo_transmute.v2.cli ingest <owner/repo>

# Legacy v1 pipeline
cd repo-transmute
PYTHONPATH=src python3 -m repo_transmute.cli ingest <owner/repo>

# Legacy v1 full pipeline
PYTHONPATH=src python3 -m repo_transmute.cli pipeline <owner/repo> --target typescript
```

## Current Status

| Phase | Status |
|-------|--------|
| Phase 1: MVP | ✅ Complete |
| Phase 2: LLM Transpilation | ✅ Complete |
| Phase 3: Compatibility & Safety | ✅ Complete |
| Phase 4: Multi-Agent Pipeline | 🔄 In Progress |
| Phase 5: Dependency Resolution | ⏳ Pending |
| Phase 6: TXTAI Semantic Layer | ⏳ Pending |
| Phase 7: Frontend Migration | ✅ Complete (v2) |

---

# v2 CLI Commands (Recommended)

v2 uses vision-driven migration with AST extraction, Playwright screenshots, LLM code generation, and self-healing verification.

## Commands

| Command | Description |
|---------|-------------|
| `v2 ingest <repo>` | Clone repo, detect framework (React/Vue/Svelte), extract AST blueprint |
| `v2 ingest --local /path` | Use local path instead of GitHub repo |
| `v2 screenshot <repo>` | Capture Playwright screenshots for visual reference |
| `v2 migrate <source> <target>` | Full migration: extract → migrate → verify → iterate |
| `v2 verify <src_ss> <tgt_ss>` | Compare source vs target screenshots (visual verification) |
| `v2 qa <reference.png>` | Autonomous QA: screenshot → compare → report → iterate |

### Examples

```bash
# Ingest a repo and extract blueprint
PYTHONPATH=src python3 -m repo_transmute.v2.cli ingest owner/repo

# Ingest from local path
PYTHONPATH=src python3 -m repo_transmute.v2.cli ingest --local /path/to/project

# Capture screenshots for visual reference
PYTHONPATH=src python3 -m repo_transmute.v2.cli screenshot owner/repo --url http://localhost:3000

# Full migration to React TypeScript
PYTHONPATH=src python3 -m repo_transmute.v2.cli migrate owner/repo target-name \
  --target-stack react-ts \
  --output-dir ./data/migrated

# Verify visual similarity
PYTHONPATH=src python3 -m repo_transmute.v2.cli verify reference.png output.png

# Autonomous QA loop (score ≥85% required)
PYTHONPATH=src python3 -m repo_transmute.v2.cli qa /tmp/reference.png \
  --live-url http://localhost:3113 \
  --iterations 3
```

---

# Legacy v1 CLI Commands

> **Note:** v1 commands are legacy. Use v2 for new migrations.

| Command | Description |
|---------|-------------|
| `ingest <repo>` | Clone repo, detect language, extract blueprint |
| `pipeline <repo> -t <target>` | Full pipeline: ingest → transpile → validate |
| `chunk <repo> -s <size>` | Split large repos into manageable chunks |
| `deps <repo>` | Analyze repository dependencies |
| `transpile <blueprint> -t <target>` | Convert blueprint to target language |
| `validate <file> -l <language>` | Validate transpiled code |
| `status` | Show cached repos and blueprints |
| `frontend_blueprint <path>` | Extract frontend blueprint (components, routes, CSS, APIs) |
| `theme_analysis <src> -t <tgt>` | Analyze theme system compatibility |
| `api_analysis <src> -t <tgt>` | Generate API migration blueprint |
| `frontend_migrate <src> <tgt>` | Full frontend migration analysis + plan |

### v1 Examples

```bash
# Ingest a repo and get its blueprint
PYTHONPATH=src python3 -m repo_transmute.cli ingest lfnovo/open-notebook

# Full pipeline with custom settings
PYTHONPATH=src python3 -m repo_transmute.cli pipeline lfnovo/open-notebook \
  --target typescript \
  --max-passes 3 \
  --model MiniMax-M2.7

# Chunk a large repo
PYTHONPATH=src python3 -m repo_transmute.cli chunk lfnovo/open-notebook --chunk-size 10

# Analyze dependencies
PYTHONPATH=src python3 -m repo_transmute.cli deps lfnovo/open-notebook -o deps.yaml

# Validate transpiled output
PYTHONPATH=src python3 -m repo_transmute.cli validate output.ts --language typescript
```

---

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Ingestion  │───▶│ Compatibility│───▶│  Blueprint  │
│   Layer     │    │   Checker   │    │  Generator  │
└─────────────┘    └─────────────┘    └─────────────┘
                                           │
                                           ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Multi-Agent │◀───│  Transpiler │───▶│   Output    │
│   Pipeline  │    │   (LLM)     │    │   Storage   │
└─────────────┘    └─────────────┘    └─────────────┘
```

### v2 Architecture (Vision-Driven)

```
┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌─────────┐
│  Ingest │──▶│ Extract │──▶│ Migrate │──▶│ Verify  │──▶│  Heal   │
│ (clone) │   │  (AST)  │   │  (LLM)  │   │(vision) │   │ (retry) │
└─────────┘   └─────────┘   └─────────┘   └─────────┘   └─────────┘
```

## Compatibility Routing

The system automatically routes based on source language:

| Source | Target | Confidence | Notes |
|--------|--------|------------|-------|
| JavaScript | TypeScript | 95% | Direct mapping |
| TypeScript | TypeScript | 98% | Same language |
| Python | Python | 90% | Keep same |
| Go | Go | 85% | Keep same |
| Rust | (keep) | - | Already Rust |
| Unknown | Skip | 0% | Cannot determine |

**Confidence Scoring:**
- ≥80%: Safe to transpile
- 50-79%: Warning issued
- <50%: Skip transpilation

## Multi-Agent Pipeline

```
CODER → REVIEWER → TDD → SECURITY
```

### Agents
- **CODER**: Ingest repos, run compatibility checks, transpile
- **REVIEWER**: Quality assurance (types, error handling, idioms)
- **TDD**: Test generation (80%+ coverage)
- **SECURITY**: OWASP audit

## Environment Variables

```bash
MINIMAX_API_KEY=sk-cp-...  # For MiniMax M2.7 transpilation
ZAI_API_KEY=...            # Backup (GLM models)
```

## Project Structure

```
repo-transmute/
├── src/repo_transmute/
│   ├── cli.py              # Legacy v1 CLI entry point
│   ├── v2/                 # v2 vision-driven engine
│   │   ├── cli.py          # v2 CLI entry point
│   │   ├── ingest/         # Clone, detect, walk
│   │   ├── extract/        # AST extraction (React/Vue/Svelte)
│   │   ├── migrate/        # Code generation + style mapping
│   │   ├── vision/         # Screenshot analysis + diff generation
│   │   ├── verify/         # Build verification + report
│   │   └── heal/           # Self-healing retry logic
│   ├── frontend/           # Legacy frontend migration modules
│   ├── transpiler/         # Legacy LLM integration
│   ├── dependency/        # Dependency graph
│   └── pipeline/           # Multi-agent coordinator
├── data/
│   ├── blueprints/         # Extracted YAML blueprints
│   ├── frontend/           # Frontend blueprints (v1)
│   ├── cache/              # Cloned repositories
│   ├── screenshots/        # Playwright screenshots (v2)
│   ├── migrated/          # Migrated components (v2 output)
│   └── outputs/           # Legacy transpiled code
├── CLAUDE.md              # Developer docs (how to extend)
├── ARCHITECTURE.md        # Detailed architecture
├── PIPELINE.md            # Multi-agent pipeline docs
└── ROADMAP.md             # Development roadmap
```

## Models

- **Primary**: MiniMax-M2.7 (via MiniMax API)
- **Fallback**: GLM-4.7 (via z.ai)

## Testing Results

| Repo | Source | Target | Confidence | Status |
|------|--------|--------|------------|--------|
| mluberry/nextjs-express | JavaScript | TypeScript | 95% | ✅ |
| shadcn-ui/next-template | TypeScript | TypeScript | 98% | ✅ |
| MunGell/awesome-for-beginners | Python | Python | 90% | ✅ |
| minimaxir/big-list-of-naughty-strings | Go | Go | 85% | ✅ |
| lfnovo/open-notebook | TypeScript/Python | Blueprint extracted | 95% | ✅ |

## Data/migrated/ Directory (v2 Output)

After v2 migration, the `data/migrated/` directory contains:

```
data/migrated/
├── MIGRATION_REPORT.md     # Summary of migration results
├── migration_report.json   # JSON report with per-component scores
├── component-name.tsx      # Migrated React components
└── ...
```

### MIGRATION_REPORT.md Contents

```markdown
## Summary

| Metric | Value |
|--------|-------|
| Total Components | 36 |
| Completed | 36 |
| Failed | 0 |
| Needs Fix | 0 |
| Success Rate | 100% |

## Per-Component Results

| Component | Status | Vision Score | Attempts |
|-----------|--------|-------------|----------|
| chat-screen.tsx | ✅ PASS | 92% | 1 |
| dashboard-screen.tsx | ✅ PASS | 88% | 1 |
...
```

## Verification & Quality Threshold

**v2 QA threshold: 85% similarity**

视觉验证使用以下维度评分：
- Overall similarity: ≥85% = PASS, <85% = FAIL
- Layout match
- Color match
- Typography match
- Spacing match

## Self-Healing (v2)

The self-healing pipeline retries failed migrations with adjusted prompts:

```python
retry_migration(component, target_stack, context, max_retries=3)
```

Each retry adds:
- Build errors from previous attempt
- Vision feedback from previous attempt
- Fix suggestions from vision model

## Frontend Migration (Phase 7 - v2)

RepoTransmute v2 supports **frontend-to-frontend migration** using vision-driven approach:

1. **AST Extraction** — Parses React/Vue/Svelte components to extract props, state, hooks, API calls
2. **Screenshot Capture** — Playwright screenshots for visual reference
3. **LLM Code Generation** — Migrate to target framework with style mapping
4. **Vision Verification** — Compare screenshots to verify visual fidelity
5. **Self-Healing** — Retry failed components with accumulated feedback

### v2 Migrate Command

```bash
PYTHONPATH=src python3 -m repo_transmute.v2.cli migrate owner/repo target-name \
  --target-stack react-ts \
  --output-dir ./data/migrated \
  --max-iterations 3
```

### v2 QA Command (Autonomous Loop)

```bash
PYTHONPATH=src python3 -m repo_transmute.v2.cli qa /tmp/reference.png \
  --live-url http://localhost:3113 \
  --iterations 3
```

## Test Results

### hermes-workspace → agent-os Migration (2026-05-09)

| Metric | Value |
|--------|-------|
| Components extracted | 761 |
| Themes extracted | 22 (11 dark + light pairs) |
| API call patterns | 125 |
| Rewrite rules generated | 125 |
| Streaming APIs detected | 5 |
| Migration confidence | 60% (SSR + high component count) |

**Successfully migrated to agent-os:**
- 11 themes via CSS variables + ThemeContext provider
- Theme picker UI in Settings page
- Terminal page (xterm.js + Docker exec PTY)
- Memory page (file browser for agent memory)
- Dashboard page (aggregated metrics)
- Updated Sidebar navigation

## Known Issues

- MiniMax returns thinking in content field — cleaned automatically
- Large repos (>30 files) may need chunking before transpilation
- TypeScript validation requires `tsc` installed

## For Developers

See [CLAUDE.md](./CLAUDE.md) for:
- How to add new language parsers
- How to add new transpilation targets
- How to add new validation steps
- Troubleshooting guide

## Documentation Links

- [CLAUDE.md](./CLAUDE.md) - Developer guide & extension points
- [ARCHITECTURE.md](./ARCHITECTURE.md) - Detailed system design
- [PIPELINE.md](./PIPELINE.md) - Multi-agent pipeline docs
- [ROADMAP.md](./ROADMAP.md) - Development roadmap

---

*Last updated: 2026-05-24*