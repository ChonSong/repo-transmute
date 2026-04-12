# RepoTransmute - AI-Powered Code Transpilation Engine

> Automate repository ingestion → blueprint generation → Rust refactoring

## Vision

AI-powered code transpilation engine:
1. Ingests repos (clone + analyze)
2. Generates language-agnostic blueprints
3. Transpiles to TypeScript, Rust, Python (Go in progress)
4. Validates output compiles
5. Provides semantic search via txtai/FAISS

**Core Language: Python** — simplifies AI/ML integration, txtai, tree-sitter

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         REPO TRANSMUTE                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐            │
│   │  Ingestion  │───▶│  Blueprint   │───▶│ Transpiler   │            │
│   │   Layer     │    │  Generator   │    │   (LLM)      │            │
│   └──────────────┘    └──────────────┘    └──────────────┘            │
│         │                     │                     │                   │
│         ▼                     ▼                     ▼                   │
│   ┌────────────────────────────────────────────────────────────────┐    │
│   │                     TXTAI LAYER                               │    │
│   │  • Embeddings (semantic search)                               │    │
│   │  • LLM orchestration (prompt chains)                         │    │
│   │  • Notebook storage                                           │    │
│   └────────────────────────────────────────────────────────────────┘    │
│                              │                                          │
│                              ▼                                          │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐            │
│   │  Dependency  │    │    Output    │    │   Frontend   │            │
│   │   Resolver   │    │   Storage    │    │  (Optional)  │            │
│   └──────────────┘    └──────────────┘    └──────────────┘            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Ingestion Layer (`src/ingestion/`)

```
src/ingestion/
├── clone.py       # Git clone (gh or git2)
├── detector.py    # Language detection
├── parser.py      # AST parsing (tree-sitter)
└── walker.py      # Recursive file traversal
```

**Dependencies:**
- `PyGithub` or `gh` CLI
- `tree-sitter` Python bindings
- `pathspec` (gitignore patterns)

---

### 2. Blueprint Generator (`src/blueprint/`)

```
src/blueprint/
├── schema.py      # Blueprint YAML schema
├── extractor.py   # Extract interfaces/functions
├── normalizer.py  # Convert to language-agnostic format
└── storage.py     # Save to YAML + index in txtai
```

**Blueprint Schema (v1):**

```yaml
version: "1.0"
source:
  repo: "owner/repo"
  url: "https://github.com/owner/repo"
  language: "python"
  framework: "fastapi"
  commit: "abc123"

blueprint:
  interfaces:
    - name: "UserService"
      type: "class"
      file: "src/services/user.py"
      line: 42
      methods:
        - name: "get_user"
          signature: "(self, id: int) -> User"
          async: true
          docstring: "Fetch a user by ID"
          
  data_structures:
    - name: "User"
      type: "class"
      fields:
        - name: "id"
          type: "int"
        - name: "email"
          type: "str"
          
  dependencies:
    external:
      - name: "pydantic"
        version: ">=2.0"
        usage: "User model definition"
    internal:
      - path: "./models/user.py"
        
  api_endpoints:
    - path: "/users/{id}"
      method: "GET"
      handler: "UserService.get_user"
      
  platform_hints:
    - "async-runtime: tokio"
    - "web-framework: axum"
    - "orm: sqlx"
```

---

### 3. Dependency Resolver (`src/dependency/`)

```
src/dependency/
├── resolver.py    # Parse and classify deps
├── registry.py     # Track processed repos
├── queue.py       # Priority queue for processing
└── registry.db    # SQLite: processed repos
```

**Resolution Strategy:**

| Type | Source | Action |
|------|--------|--------|
| External | PyPI, npm, crates.io | Check for Rust equivalent or create binding |
| Internal | Local modules | Process recursively |
| Sibling | Same org repos | Clone and process |

---

### 4. Transpiler Engine (`src/transpiler/`)

```
src/transpiler/
├── llm.py         # txtai LLM orchestration
├── prompts.py     # Prompt templates
├── formatter.py   # rustfmt integration
└── validator.py   # cargo check integration
```

**Transpilation Flow:**

```
Blueprint (YAML)
       │
       ▼
┌─────────────────┐
│  txtai pipeline │
│                 │
│  Prompt:        │
│  "Convert this  │
│   blueprint to  │
│   idiomatic     │
│   Rust..."      │
└─────────────────┘
       │
       ▼
   Rust code
       │
       ▼
┌─────────────┐
│  rustfmt    │──▶ Formatted Rust
└─────────────┘
       │
       ▼
┌─────────────┐
│ cargo check │──▶ Valid? Yes → Save
└─────────────┘     No → Log error, emit partial
```

**Example Prompt:**

```
You are an expert Rust developer. Convert this blueprint to idiomatic Rust.

Blueprint:
```yaml
interfaces:
  - name: "UserService"
    type: "class"
    methods:
      - name: "get_user"
        signature: "(id: i32) -> User"
        async: true
        
data_structures:
  - name: "User"
    fields:
      - name: "id"
        type: "i32"
      - name: "email"
        type: "String"
```

Requirements:
- Use Axum for HTTP handlers
- Use Serde for serialization (#[derive(Serialize, Deserialize)])
- Use Tokio for async (#[tokio::main])
- Use sqlx or sea-orm for database if needed
- Follow Rust naming conventions (snake_case)
- Handle errors with Result<T, Box<dyn Error>> or custom error types
- Add proper error handling with anyhow
- Use async traits if needed (async_trait crate)

Output ONLY the Rust code, no explanations.
```

---

### 5. TXTAI Integration (`src/txtai/`)

```
src/txtai/
├── client.py      # txtai API client
├── indexer.py     # Index blueprints
├── search.py      # Semantic search
├── notebook.py    # Notebook storage
└── pipeline.py    # LLM orchestration
```

**TXTAI Capabilities:**

```python
# Semantic search across blueprints
txtai.search("find similar user authentication patterns across all repos")

# Cross-repo pattern discovery  
txtai.search("how does caching work in other Python repos in the index")

# LLM orchestration
txtai.extract("summarize the API endpoints in this blueprint")
txtai.transform("convert this Python blueprint to Go using standard libraries")
```

**Index Schema:**

```json
{
  "id": "repo:commit:file",
  "text": "UserService.get_user(id: int) -> User",
  "blueprint": { ... },
  "rust_output": "...",
  "repo": "owner/repo",
  "language": "python"
}
```

---

### 6. Frontend Unification (Planned)

Screenshot-based component reconstruction using Playwright + LLM vision analysis. See ROADMAP.md Phase 9 for current status.

---

### 7. Storage & State

```
repo-transmute/
├── data/
│   ├── blueprints/     # YAML blueprints (versioned)
│   ├── outputs/       # Generated Rust code
│   ├── screenshots/   # Frontend captures
│   └── notebooks/     # TXTAI-style notebooks
├── cache/             # Cloned repos (cleaned after processing)
├── registry.db        # SQLite: processed repos, deps
└── txtai/             # txtai index (or use external)
```

---

## Heartbeat Scheduling

```
┌─────────────────────────────────────────────────────────────────┐
│                     HEARTBEAT SCHEDULER                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   OpenClaw Heartbeat (~30 min)                                 │
│         │                                                      │
│         ▼                                                      │
│   ┌─────────────────────────────────────────────────────────┐  │
│   │  1. Check queue for pending repos                       │  │
│   │  2. Pick highest priority                                │  │
│   │  3. Run: clone → parse → blueprint → transpile           │  │
│   │  4. Index in txtai                                      │  │
│   │  5. Queue dependencies                                   │  │
│   │  6. Update status                                        │  │
│   └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│   Rate limits: GitHub API (5000/hr authenticated)              │
│   Max concurrent: 2-3 repos                                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: MVP (Week 1-2)

**Goal:** End-to-end proof of concept with one repo

- [ ] **1.1** Project setup (`pyproject.toml`, dependencies)
- [ ] **1.2** Clone service (gh CLI or PyGithub)
- [ ] **1.3** Language detection + file walker
- [ ] **1.4** Basic blueprint generator (functions + classes only)
- [ ] **1.5** Save blueprint to YAML
- [ ] **1.6** Test with 1 repo (e.g., `clean-code-javascript`)

**Deliverable:** Manual run produces a YAML blueprint for one repo

### Phase 2: LLM Integration (Week 2-3)

- [ ] **2.1** txtai setup (local or cloud)
- [ ] **2.2** Prompt templates for transpilation
- [ ] **2.3** LLM transpilation (Python → Rust)
- [ ] **2.4** rustfmt + cargo check validation
- [ ] **2.5** Store outputs

**Deliverable:** One repo transpiled to Rust with valid code

### Phase 3: Dependency Resolution (Week 3-4)

- [ ] **3.1** Parse requirements.txt, package.json, Cargo.toml
- [ ] **3.2** Dependency classifier (external vs internal)
- [ ] **3.3** Queue system with SQLite
- [ ] **3.4** Recursive processing

**Deliverable:** Auto-queues and processes dependencies

### Phase 4: TXTAI Semantic Layer (Week 4-5)

- [ ] **4.1** Index blueprints in txtai
- [ ] **4.2** Semantic search API
- [ ] **4.3** Cross-repo pattern queries
- [ ] **4.4** Notebook storage

**Deliverable:** "Find similar patterns" queries work

### Phase 5: Frontend (Week 5-6)

- [ ] **5.1** Screenshot capture with Playwright
- [ ] **5.2** Vision → component blueprint
- [ ] **5.3** Leptos/Dioxus generator

**Deliverable:** Screenshot → Rust component works

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ |
| Packaging | `pyproject.toml` / `poetry` |
| AST Parsing | `tree-sitter` |
| Git | `PyGithub` or `gh` CLI |
| AI/LLM | `txtai` (local or remote) |
| Vector Store | txtai embeddings (or Milvus) |
| Database | SQLite |
| Frontend Capture | Playwright |
| Target Frontend | Leptos or Dioxus (generated) |

---

## File Structure

```
repo-transmute/
├── pyproject.toml
├── README.md
├── ARCHITECTURE.md
├── src/
│   └── repo_transmute/
│       ├── __init__.py
│       ├── cli.py              # CLI entry point
│       ├── config.py           # Configuration
│       ├── ingestion/
│       │   ├── __init__.py
│       │   ├── clone.py
│       │   ├── detector.py
│       │   ├── parser.py
│       │   └── walker.py
│       ├── blueprint/
│       │   ├── __init__.py
│       │   ├── schema.py
│       │   ├── extractor.py
│       │   ├── normalizer.py
│       │   └── storage.py
│       ├── dependency/
│       │   ├── __init__.py
│       │   ├── resolver.py
│       │   ├── queue.py
│       │   └── registry.py
│       ├── transpiler/
│       │   ├── __init__.py
│       │   ├── llm.py
│       │   ├── prompts.py
│       │   ├── formatter.py
│       │   └── validator.py
│       ├── txtai/
│       │   ├── __init__.py
│       │   ├── client.py
│       │   ├── indexer.py
│       │   ├── search.py
│       │   └── notebook.py
│       └── frontend/
│           ├── __init__.py
│           ├── capture.py
│           ├── vision.py
│           └── generator.py
├── data/
│   ├── blueprints/
│   ├── outputs/
│   └── cache/
└── tests/
    └── ...
```

---

## Related Tools

- **Rhiza** — Template management (for generated repo structure)
- **txtai** — Semantic search + LLM orchestration
- **tree-sitter** — AST parsing
- **Milvus** — Vector store (if txtai uses external backend)
- **Leptos/Dioxus** — Target frontend frameworks

---

*Last updated: 2026-03-20*
