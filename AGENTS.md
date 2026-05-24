# AGENTS.md — repo-transmute v2

## About
AI-powered code migration engine. v2: AST extraction (React/Vue/Svelte), Playwright screenshots, LLM migration, vision verification, self-healing.

## Quick Start
```bash
cd /home/hermeswebui/.hermes/repo-transmute-v2
PYTHONPATH=src python3 -m repo_transmute.v2.cli ingest <owner/repo>
```

## Architecture
- **src/repo_transmute/v2/** — Core v2 engine
  - `ingest/` — Clone, detect framework (React/Vue/Svelte), walk project
  - `extract/` — AST extraction for components, routes, styles, API calls
  - `migrate/` — Code generation + style mapping + API rewriting
  - `vision/` — Screenshot analysis, similarity scoring, diff generation
  - `verify/` — Build verification, screenshot compare, migration report
  - `heal/` — Self-healing: retry migration with accumulated feedback
- **data/** — Extracted blueprints, cached repos, migrated output
- **scripts/** — Helper scripts for batch processing

## v2 CLI Commands

| Command | Description |
|---------|-------------|
| `v2 ingest <repo>` | Clone repo, detect framework, extract AST blueprint |
| `v2 ingest --local /path` | Use local path instead of GitHub |
| `v2 screenshot <repo>` | Capture screenshots for visual reference |
| `v2 migrate <source> <target>` | Full migration: extract → migrate → verify → iterate |
| `v2 verify <src_ss> <tgt_ss>` | Compare source vs target screenshots (visual verification) |
| `v2 qa <reference.png>` | Visual QA: screenshot → compare → report → iterate |

### Examples
```bash
# Ingest and extract blueprint
PYTHONPATH=src python3 -m repo_transmute.v2.cli ingest owner/repo

# Ingest from local path
PYTHONPATH=src python3 -m repo_transmute.v2.cli ingest --local /path/to/project

# Screenshot capture
PYTHONPATH=src python3 -m repo_transmute.v2.cli screenshot owner/repo --url http://localhost:3000

# Full migration
PYTHONPATH=src python3 -m repo_transmute.v2.cli migrate owner/repo target-name --target-stack react-ts

# Visual verification
PYTHONPATH=src python3 -m repo_transmute.v2.cli verify reference.png output.png

# Autonomous QA loop
PYTHONPATH=src python3 -m repo_transmute.v2.cli qa /tmp/reference.png --live-url http://localhost:3113
```

## Data/ Output Directory

```
data/
├── blueprints/          # Extracted YAML blueprints (AST, routes, styles, APIs)
├── cache/              # Cloned repositories
├── migrated/           # Migrated components (tsx files + MIGRATION_REPORT.md)
└── screenshots/        # Playwright screenshots for visual reference
```

## Verification & Quality Threshold

**QA threshold: 85% similarity** — Components must score ≥85% on vision comparison to pass.

```
Overall similarity: {score:.0%}  (≥85% = PASS, <85% = FAIL)
Layout match: ✅/❌
Color match: ✅/❌
Typography match: ✅/❌
Spacing match: ✅/❌
```

## Self-Healing

The self-healing pipeline retries failed migrations with adjusted prompts:

```python
retry_migration(component, target_stack, context, max_retries=3)
```

Each retry adds:
- Build errors from previous attempt
- Vision feedback from previous attempt
- Fix suggestions from vision model

## Integration
- **Consumes:** seans-reporepo candidates/ as migration input
- **Outputs:** Migrated components → hermes-web-computer (Go + Svelte 5)
- **Extracted:** 629 components + 263 APIs from hermes-workspace
- **Migrated:** 36 components to agent-os format (768KB)

## Tests
```bash
cd /home/hermeswebui/.hermes/repo-transmute-v2
python -m pytest tests/  # 12/12 passing
```

## Key Files
- `PIPELINE.md` — Migration pipeline stages
- `ARCHITECTURE.md` — System architecture
- `ROADMAP.md` — Future development plan
- `CLAUDE.md` — Claude-specific instructions
- `src/repo_transmute/cli.py` — Legacy v1 CLI entry point
- `src/repo_transmute/v2/cli.py` — v2 CLI entry point

## Notes
- v2 uses vision-driven migration (screenshot + LLM + verify loop)
- AST extraction handles React, Vue, and Svelte component parsing
- Self-healing retries up to 3 times with accumulated fix context
- QA threshold is 85% similarity for visual verification pass