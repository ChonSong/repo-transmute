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
# Clone repo and extract blueprint
cd repo-transmute
PYTHONPATH=src python3 -m repo_transmute.cli ingest <owner/repo>

# Or run full pipeline (ingest + transpile + validate)
PYTHONPATH=src python3 -m repo_transmute.cli pipeline <owner/repo> --target typescript

# Check status
PYTHONPATH=src python3 -m repo_transmute.cli status
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
| Phase 7: Frontend Migration | ✅ Complete |

## CLI Commands

| Command | Description |
|---------|-------------|
| `ingest <repo>` | Clone repo, detect language, extract blueprint |
| `pipeline <repo> -t <target>` | Full pipeline: ingest → transpile → validate |
| `chunk <repo> -s <size>` | Split large repos into manageable chunks |
| `deps <repo>` | Analyze repository dependencies |
| `transpile <blueprint> -t <target>` | Convert blueprint to target language |
| `validate <file> -l <language>` | Validate transpiled code |
| `status` | Show cached repos and blueprints |
| **`frontend_blueprint <path>`** | **Extract frontend blueprint (components, routes, CSS, APIs)** |
| **`theme_analysis <src> -t <tgt>`** | **Analyze theme system compatibility** |
| **`api_analysis <src> -t <tgt>`** | **Generate API migration blueprint** |
| **`frontend_migrate <src> <tgt>`** | **Full frontend migration analysis + plan** |

### Examples

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
│   ├── cli.py              # CLI entry point (backend + frontend commands)
│   ├── ingestion/          # Clone, detect, walk
│   ├── blueprint/          # Extract, storage
│   ├── frontend/           # **NEW** Frontend migration modules
│   │   ├── component_extractor.py  # JSX/TSX component parsing
│   │   ├── css_mapper.py           # CSS/theme extraction + mapping
│   │   └── api_rewriter.py         # API call pattern detection
│   ├── transpiler/         # LLM integration
│   │   ├── llm.py         # API calls
│   │   ├── prompts.py     # Prompt templates (backend + frontend)
│   │   ├── compatibility.py # Routing table (backend + frontend)
│   │   └── validate.py    # Output validation (Rust, TS, Python, React)
│   ├── dependency/         # Dependency graph
│   └── pipeline/           # Multi-agent coordinator
├── data/
│   ├── blueprints/         # YAML blueprints
│   ├── frontend/           # Frontend blueprints
│   ├── outputs/           # Transpiled code
│   └── cache/             # Cloned repos
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

## Frontend Migration (Phase 7)

RepoTransmute now supports **frontend-to-frontend migration** — moving React components, CSS themes, and API patterns between projects.

### What it does

1. **Component Extraction** — Parses JSX/TSX files to extract component structure (props, state, hooks, children, API calls, CSS approach)
2. **Theme Analysis** — Extracts CSS variable themes, detects approach (css-vars, tailwind, styled-components), compares compatibility
3. **API Pattern Detection** — Finds all fetch/axios/EventSource/WebSocket calls, generates URL mapping rules
4. **Compatibility Scoring** — Rates migration feasibility based on framework, component count, SSR usage, theme compatibility

### Example

```bash
# Extract frontend blueprint
PYTHONPATH=src python3 -m repo_transmute.cli frontend_blueprint /path/to/source-project

# Compare theme systems
PYTHONPATH=src python3 -m repo_transmute.cli theme_analysis /path/to/source -t /path/to/target

# Analyze API patterns
PYTHONPATH=src python3 -m repo_transmute.cli api_analysis /path/to/source -t /path/to/target

# Full migration analysis
PYTHONPATH=src python3 -m repo_transmute.cli frontend_migrate /path/to/source /path/to/target \
  --framework react --style tailwind --dry-run
```

### Modules

| Module | Purpose |
|--------|---------|
| `frontend/component_extractor.py` | JSX/TSX component + route extraction |
| `frontend/css_mapper.py` | CSS variable/theme extraction + compatibility analysis |
| `frontend/api_rewriter.py` | API call pattern detection + rewrite rule generation |
| `transpiler/prompts.py` | Frontend migration LLM prompts |
| `transpiler/validate.py` | React/TSX validation (tsc + vite build + syntax check) |
| `transpiler/compatibility.py` | Frontend routing table + compatibility checker |

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

*Last updated: 2026-03-20*
