# AGENTS.md — repo-transmute

## About
AI-powered code migration engine. v2: AST extraction (React/Vue/Svelte), Playwright screenshots, LLM migration, vision verification, self-healing.

## Quick Start
```bash
cd /opt/data/repo-transmute-v2
PYTHONPATH=src python3 -m repo_transmute.cli ingest <owner/repo>
```

## Architecture
- **src/repo_transmute/** — Core engine
  - AST extraction for React/Vue/Svelte components
  - Playwright screenshot capture for visual verification
  - LLM-powered migration with vision-based validation
  - Self-healing pipeline for failed migrations
- **data/** — Extracted components, blueprints, migration artifacts
- **scripts/** — Helper scripts for batch processing

## Key Files
- `PIPELINE.md` — Migration pipeline stages
- `ARCHITECTURE.md` — System architecture
- `ROADMAP.md` — Future development plan
- `CLAUDE.md` — Claude-specific instructions
- `src/repo_transmute/cli.py` — CLI entry point

## Integration
- **Consumes:** seans-reporepo candidates/ as migration input
- **Outputs:** Migrated components → hermes-web-computer (Go + Svelte 5)
- **Extracted:** 629 components + 263 APIs from hermes-workspace
- **Migrated:** 36 components to agent-os format (768KB)

## Tests
```bash
cd /opt/data/repo-transmute-v2
python -m pytest tests/  # 12/12 passing
```

## Notes
- v2 focuses on vision-driven migration (screenshot + LLM + verify loop)
- AST extraction handles React, Vue, and Svelte component parsing
- Self-healing retries failed migrations with adjusted prompts
