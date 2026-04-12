# RepoTransmute - AI-Powered Code Transpilation Engine

> Automated repository ingestion → compatibility checking → blueprint generation → transpilation

## Project Overview

RepoTransmute is an AI-powered code transpilation engine that:
1. **Ingests** repositories (clones + analyzes source code)
2. **Validates** compatibility (source → target language routing)
3. **Generates** language-agnostic blueprints (YAML format)
4. **Transpiles** code to target languages using LLM (MiniMax M2.7, GLM-4 fallback)
5. **Validates** output code (TypeScript tsc, Rust cargo, Python py_compile)

### Current Status

| Phase | Status |
|-------|--------|
| Phase 1: MVP | ✅ Complete |
| Phase 2: LLM Transpilation | ✅ Complete |
| Phase 3: Compatibility & Safety | ✅ Complete |
| Phase 4: Multi-Agent Pipeline | ✅ Complete |
| Phase 5: Dependency Resolution | ⏳ Pending |
| Phase 6: TXTAI Semantic Layer | ⏳ Pending |
| Phase 7: Frontend Unification | ⏳ Pending |

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

### Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| **CLI** | `src/repo_transmute/cli.py` | Entry point for all commands |
| **Ingestion** | `src/repo_transmute/ingestion/` | Clone, detect language, walk files |
| **Blueprint** | `src/repo_transmute/blueprint/` | Extract & store code metadata |
| **Transpiler** | `src/repo_transmute/transpiler/` | LLM integration, prompts, validation |
| **Dependency** | `src/repo_transmute/dependency/` | Dependency graph analysis |
| **Pipeline** | `src/repo_transmute/pipeline/` | Multi-agent coordinator |

---

## Quick Start

### Phase 1: Ingest (Clone & Extract Blueprint)

```bash
cd repo-transmute
PYTHONPATH=src python3 -m repo_transmute.cli ingest <owner/repo>

# Example
PYTHONPATH=src python3 -m repo_transmute.cli ingest lfnovo/open-notebook
```

### Phase 2: Transpile (Convert to Target Language)

```bash
# Using existing blueprint
PYTHONPATH=src python3 -m repo_transmute.cli transpile data/blueprints/<repo>.yaml --target typescript

# Or use pipeline command (full end-to-end)
PYTHONPATH=src python3 -m repo_transmute.cli pipeline <owner/repo> --target typescript
```

### Phase 3: Validate

```bash
PYTHONPATH=src python3 -m repo_transmute.cli validate <file> --language typescript
```

### Phase 4: Status & Utilities

```bash
# Check status
PYTHONPATH=src python3 -m repo_transmute.cli status

# Chunk large repos
PYTHONPATH=src python3 -m repo_transmute.cli chunk <owner/repo> --chunk-size 20

# Analyze dependencies
PYTHONPATH=src python3 -m repo_transmute.cli deps <owner/repo>
```

---

## CLI Commands Reference

| Command | Description |
|---------|-------------|
| `ingest <repo>` | Clone repo, detect language, extract blueprint |
| `pipeline <repo>` | Full pipeline: ingest → transpile → validate |
| `chunk <repo>` | Split repo into manageable chunks |
| `deps <repo>` | Analyze repository dependencies |
| `transpile <blueprint>` | Convert blueprint to target language |
| `validate <file>` | Validate transpiled code |
| `search <query>` | Search indexed blueprints (Phase 6) |
| `status` | Show cached repos and blueprints |

---

## For Developers

### Adding New Language Parsers

Located in `src/repo_transmute/ingestion/`

1. Create a new detector or extend `detector.py`:

```python
# In detector.py, add to LANGUAGE_PATTERNS
LANGUAGE_PATTERNS = {
    ...
    "kotlin": ["*.kt", "*.kts"],
    "swift": ["*.swift"],
}

# Add detection logic
def detect_language(repo_path: Path) -> Optional[str]:
    ...
```

2. Update routing table in `transpiler/compatibility.py`:

```python
ROUTING_TABLE = {
    ...
    Language.KOTLIN: (TargetLanguage.RUST, 0.6, "Kotlin to Rust"),
}
```

### Adding New Transpilation Targets

Located in `src/repo_transmute/transpiler/`

1. **Add prompt template** in `prompts.py`:

```python
PYTHON_TO_GO_PROMPT = """You are an expert Python to Go developer..."""
```

2. **Update routing** in `compatibility.py`:

```python
class TargetLanguage(Enum):
    ...
    GO = "go"  # Add this
```

3. **Add validation** in `validate.py`:

```python
def validate_go(file_path: Path) -> ValidationResult:
    """Validate Go using go vet or build."""
    ...
```

4. **Wire up** in `llm.py` - update `transpile_with_llm()` to handle new target.

### Adding New Validation Steps

In `src/repo_transmute/transpiler/validate.py`:

```python
def validate_something(file_path: Path, language: str) -> ValidationResult:
    """Custom validation logic."""
    # Add your checks here
    return ValidationResult(success=True, output="Passed")

# Add to main validate() function
def validate(file_path: Path, language: str) -> ValidationResult:
    ...
    if "something" in lang:
        return validate_something(file_path, language)
```

---

## Open-Notebook Specific

The `lfnovo/open-notebook` repo is a complex multi-language project with:

- **Frontend**: TypeScript (Next.js)
- **Backend**: Python (FastAPI/SurrealDB)
- **AI Components**: Python modules

### Transpiling Open-Notebook

```bash
# Full pipeline with high max-passes for complex repos
PYTHONPATH=src python3 -m repo_transmute.cli pipeline lfnovo/open-notebook \
  --target typescript \
  --max-passes 3

# Or just ingest first to see compatibility
PYTHONPATH=src python3 -m repo_transmute.cli ingest lfnovo/open-notebook
```

### Known Issues with Open-Notebook

1. **High complexity** (>500 functions) - may need chunking
2. **Mixed languages** - frontend/backend need separate pipelines
3. **Many dependencies** - Phase 5 handles this better

### Best Practice for Large Repos

```bash
# 1. Chunk first
PYTHONPATH=src python3 -m repo_transmute.cli chunk lfnovo/open-notebook --chunk-size 10

# 2. Transpile each chunk separately
PYTHONPATH=src python3 -m repo_transmute.cli transpile data/blueprints/open-notebook.chunk1.yaml

# 3. Validate each output
PYTHONPATH=src python3 -m repo_transmute.cli validate output.ts --language typescript
```

---

## Troubleshooting

### Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `MINIMAX_API_KEY` not set | Missing API key | Set `MINIMAX_API_KEY=sk-cp-...` |
| Language not detected | No source files found | Ensure repo has `.py`, `.js`, or `.ts` files |
| Transpilation timeout | Large repo | Use `--max-passes 1` or chunk first |
| Validation fails | Syntax errors in output | Check LLM output, may need prompt tuning |
| "Unknown language" | Not in routing table | Add to `ROUTING_TABLE` in compatibility.py |

### Debug Mode

```bash
# Enable verbose output
export PYTHONPATH=src
python3 -m repo_transmute.cli ingest owner/repo -v
```

### Environment Variables

```bash
MINIMAX_API_KEY=sk-cp-...  # Primary: MiniMax M2.7
ZAI_API_KEY=...            # Fallback: GLM-4
```

---

## Project Structure

```
repo-transmute/
├── src/repo_transmute/
│   ├── cli.py                  # CLI entry point
│   ├── ingestion/              # Clone, detect, walk
│   │   ├── clone.py
│   │   ├── detector.py
│   │   └── walker.py
│   ├── blueprint/              # Extract, storage
│   │   ├── extractor.py
│   │   └── storage.py
│   ├── transpiler/              # LLM integration
│   │   ├── llm.py             # API calls
│   │   ├── prompts.py         # Prompt templates
│   │   ├── compatibility.py  # Routing table
│   │   └── validate.py       # Output validation
│   ├── dependency/             # Dependency graph
│   └── pipeline/               # Multi-agent coordinator
├── data/
│   ├── blueprints/             # YAML blueprints
│   ├── outputs/               # Transpiled code
│   └── cache/                 # Cloned repos
├── CLAUDE.md                   # This file
├── README.md                   # User-facing docs
├── ARCHITECTURE.md            # Detailed architecture
└── README.md (Multi-Agent Pipeline section)                # Multi-agent pipeline docs
```

---

*For more details, see [ARCHITECTURE.md](./ARCHITECTURE.md) and [README.md (Multi-Agent Pipeline section)](./README.md (Multi-Agent Pipeline section))*
