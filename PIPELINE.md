# Multi-Agent Pipeline

> Automated quality gates for RepoTransmute

## Overview

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   CODER     │───▶│  REVIEWER   │───▶│    TDD      │───▶│  SECURITY   │
│  (Agent)    │    │  (Agent)    │    │  (Agent)    │    │  (Agent)    │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
      │                 │                 │                 │
      ▼                 ▼                 ▼                 ▼
  Ingest +         Quality           Test             Security
  Transpile        Review            Generation       Audit
```

## Agent Roles

### CODER Agent
- **Role:** Ingest repos, run compatibility checks, transpile
- **Commands:**
  - `repo-transmute ingest <repo>` - Clone + analyze
  - `repo-transmute transpile <blueprint>` - Generate code
- **Success Criteria:** Confidence >= 80%, transpile completes

### REVIEWER Agent
- **Role:** Quality assurance
- **Checks:**
  - Type definitions present
  - Error handling exists
  - Code is idiomatic
  - No obvious bugs
- **Success Criteria:** Quality score >= 7/10

### TDD Agent
- **Role:** Test generation
- **Tools:** Uses tdd-guide patterns
- **Success Criteria:** Tests cover >= 80% of code

### SECURITY Agent
- **Role:** Security audit
- **Checks:** OWASP Top 10, secrets, injection
- **Success Criteria:** No critical issues

## Usage

### Manual Pipeline

```bash
# Step 1: Ingest
PYTHONPATH=src python3 -m repo_transmute.cli ingest <repo>

# Step 2: Reviewer reviews output
# (spawn reviewer agent)

# Step 3: TDD generates tests
# (spawn tdd-guide agent)

# Step 4: Security audit
# (spawn security-reviewer agent)
```

### Automated Pipeline (via OpenClaw)

```bash
# Spawn pipeline agents
openclaw agents spawn coder --task "Ingest and transpile repo"
openclaw agents spawn reviewer --task "Review transpiled code"
openclaw agents spawn tdd --task "Generate tests"
```

## Configuration

### Environment Variables
```bash
MINIMAX_API_KEY=sk-cp-...  # For transpilation
ZAI_API_KEY=...            # Backup
```

### Model Settings
- **Coder:** MiniMax-M2.7 (best for code gen)
- **Reviewer:** MiniMax-M2.7 (reasoning)
- **TDD:** MiniMax-M2.7 (test generation)
- **Security:** MiniMax-M2.7 (analysis)

## Results

| Repo | Source | Target | Confidence | Quality |
|------|--------|--------|------------|---------|
| mluberry/nextjs-express | JavaScript | TypeScript | 95% | TBD |
| MunGell/awesome-for-beginners | Python | Python | 90% | TBD |

---

*Last updated: 2026-03-20*
