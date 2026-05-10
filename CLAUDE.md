# RepoTransmute v2 — Vision-Driven Code Migration Engine

> Automated repository ingestion → AST extraction → visual analysis → LLM migration → vision verification → self-healing

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      repo-transmute v2                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  INGEST → EXTRACT → PLAN → MIGRATE → VERIFY → ITERATE          │
│                                                                 │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐                  │
│  │ INGEST   │───▶│ EXTRACT  │───▶│  PLAN    │                  │
│  │          │    │ (AST +   │    │          │                  │
│  │ Clone    │    │  Vision) │    │ Order +  │                  │
│  │ Detect   │    │          │    │ Style    │                  │
│  └──────────┘    └──────────┘    └────┬─────┘                  │
│                                       │                         │
│                              ┌────────▼─────────┐              │
│                              │    MIGRATE       │              │
│                              │ (LLM + Context)  │              │
│                              └────────┬─────────┘              │
│                                       │                         │
│                              ┌────────▼─────────┐              │
│                              │    VERIFY        │              │
│                              │ (Vision Score)   │              │
│                              └────────┬─────────┘              │
│                                       │                         │
│                              ┌────────▼─────────┐              │
│                              │    ITERATE       │              │
│                              │ (Self-Healing)   │              │
│                              └──────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

## Module Structure

```
repo_transmute/
├── v2/
│   ├── ingest/
│   │   ├── clone.py              # Git clone + branch handling
│   │   ├── detector.py           # Framework detection (React/Vue/Svelte/etc.)
│   │   └── walker.py             # Smart file tree traversal
│   ├── extract/
│   │   ├── ast_extractor.py      # Multi-framework AST parsing
│   │   ├── style_extractor.py    # CSS/Tailwind/design token extraction
│   │   ├── api_extractor.py      # API call pattern extraction
│   │   └── screenshot.py         # Playwright page capture + component screenshots
│   ├── vision/
│   │   ├── analyzer.py           # Vision model: layout analysis, component matching
│   │   ├── scorer.py             # Pixel-perfection scoring between source/target
│   │   └── diff_generator.py     # Visual diff with annotations
│   ├── migrate/
│   │   ├── engine.py             # LLM-driven migration with context assembly
│   │   ├── style_mapper.py       # Cross-stack style system mapping
│   │   ├── api_rewriter.py       # API endpoint adaptation
│   │   └── codegen.py            # Code generation with framework-specific templates
│   ├── verify/
│   │   ├── build.py              # Build target project, capture screenshots
│   │   ├── compare.py            # Vision comparison: source vs target
│   │   └── report.py             # Migration quality report
│   ├── heal/
│   │   ├── fix_generator.py      # Generate fix prompts from vision feedback
│   │   ├── retry.py              # Iterative migration with improved context
│   │   └── fallback.py           # Fallback strategies when vision can't verify
│   ├── cli.py                    # New CLI for v2 commands
│   └── models.py                 # Data models (Component, Page, StyleSystem, etc.)
├── cli.py                        # Legacy CLI (preserved)
├── ingestion/                    # Legacy modules (preserved)
├── blueprint/                    # Legacy modules (preserved)
├── transpiler/                   # Legacy modules (preserved)
├── frontend/                     # Legacy modules (preserved)
└── pipeline/                     # Legacy modules (preserved)
```

## CLI Commands (v2)

| Command | Description |
|---------|-------------|
| `v2 ingest <repo>` | Clone + detect framework + extract AST blueprint |
| `v2 screenshot <repo> --url` | Capture screenshots of all pages |
| `v2 migrate <source> <target> --framework react --target-stack react` | Full migration with vision loop |
| `v2 verify <source> <target>` | Compare source vs target screenshots |
| `v2 status` | Show migration progress |

## Key Design Decisions

1. **Vision-first verification** — Every migrated component/page is screenshot and compared to source
2. **Framework-agnostic** — Detection at ingest time, correct parser selected automatically
3. **Iterative self-healing** — If vision scores below threshold, auto-generate fix prompts
4. **Incremental migration** — Migrate one component at a time, verify before proceeding
5. **Context assembly** — Gather source code, screenshots, style tokens, API patterns as context for LLM
