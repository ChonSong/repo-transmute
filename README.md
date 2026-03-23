# Repo Transmute

**AI-powered code transpilation engine** — ingests repositories, validates compatibility, transpiles to TypeScript/Rust/Python via LLM, and indexes for semantic search.

---

## What It Does

```
GitHub Repo (any language)
       │
       ▼
┌──────────────┐    ┌────────────────┐    ┌─────────────────────┐
│   INGEST     │───▶│  COMPATIBILITY │───▶│  TRANSPILE          │
│  Clone +     │    │  Check         │    │  LLM-powered        │
│  Blueprint   │    │  Confidence %  │    │  Multi-pass         │
└──────────────┘    └────────────────┘    └─────────────────────┘
                                                  │
                                                  ▼
                                          ┌──────────────┐
                                          │ VALIDATE     │
                                          │ tsc / cargo  │
                                          └──────────────┘
```

## Features

- **Language Detection** — Auto-detects Python, TypeScript, JavaScript, Rust
- **Blueprint Extraction** — Full function bodies, signatures, docstrings, decorators
- **Module-Aware Chunking** — Handles repos up to 10k+ functions with dependency tracking
- **Compatibility Routing** — Source → Target confidence scoring before transpiling
- **Multi-Pass Transpilation** — Initial + refinement + validation loops
- **Multi-Agent Pipeline** — Coder → Reviewer → TDD agent flow
- **Semantic Search** — Local embeddings (sentence-transformers) + Milvus vector store
- **Directory Structure** — Preserves module/file hierarchy in output

## Installation

```bash
pip install -e .
```

## CLI Commands

```bash
# Ingest a repo (clone + extract blueprint)
repo-transmute ingest owner/repo

# Run full pipeline (ingest + transpile + validate)
repo-transmute pipeline owner/repo -t typescript

# Chunk a repo for inspection
repo-transmute chunk owner/repo --chunk-size 20

# Analyze dependencies
repo-transmute deps owner/repo

# Validate transpiled output
repo-transmute validate output.ts -l typescript
```

## Repo Reaper (Semantic Search)

```bash
# Index a repository for semantic search
repo-reaper index /path/to/repo --repo-name owner/repo

# Search indexed code
repo-reaper search "agent loop implementation" --repo HKUDS/nanobot

# Build LLM context from search results
repo-reaper context "MCP server dashboard" --include-body

# Index all cached repos
repo-reaper index-all data/cache
```

## Architecture

```
src/repo_transmute/
├── ingestion/        # Clone, detect language, walk files
├── blueprint/        # Extract functions, classes, bodies → YAML
├── transpiler/
│   ├── chunker.py   # Module-aware chunking + Reassembler
│   ├── llm.py       # MiniMax / z.ai API integration
│   ├── prompts.py   # Language-specific transpilation prompts
│   ├── compatibility.py  # Source→Target routing table
│   └── validate.py  # tsc / cargo check / py_compile
├── pipeline/
│   └── coordinator.py  # Multi-pass pipeline orchestration
└── cli.py           # CLI interface

src/repo_reaper/
├── embedder.py      # sentence-transformers (CPU/GPU)
├── indexer.py       # Milvus + SQLite fallback
└── rag.py           # Semantic search + context builder
```

## Supported Languages

| Source | Target | Status |
|--------|--------|--------|
| Python | TypeScript | ✅ Production |
| Python | Rust | ✅ Production |
| Python | Python | ✅ Production |
| TypeScript | TypeScript | ✅ Production |
| JavaScript | TypeScript | ✅ Production |
| Python | TSX/React | ✅ With TSX template |
| Go | Any | ⏳ Planned |
| Java | Any | ⏳ Planned |

## Requirements

- Python ≥ 3.10
- MiniMax or z.ai API key for LLM calls
- Milvus (optional) for semantic search
- sentence-transformers for local embeddings
- tsc / cargo / python for validation (target-dependent)

## Environment Variables

```bash
MINIMAX_API_KEY=...   # MiniMax API key (required for transpilation)
ZAI_API_KEY=...       # z.ai GLM key (alternative to MiniMax)
MILVUS_URI=...        # Milvus server (default: http://localhost:19530)
HF_TOKEN=...          # HuggingFace token (optional, for faster model downloads)
```
