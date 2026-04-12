# RepoTransmute Enhancement Plan

## Phase 1: Dependency Resolution (Priority)
- Parse import/export statements
- Build dependency graph
- Queue system for recursive processing
- Process entry points first

## Phase 2: Chunking for Large Repos
- Split by file/module boundaries (not arbitrary limits)
- Preserve import relationships
- Reassemble transpiled chunks
- Handle cross-chunk references

## Phase 3: Sophisticated Pipeline
- Multi-pass refinement
- Type-aware transpilation
- Test generation per chunk
- Integration validation

## Tasks

### Phase 1 Tasks
1. Add import parser for TypeScript/JavaScript
2. Build module graph
3. Implement queue with topological sort
4. Process in dependency order

### Phase 2 Tasks
1. Chunk by file/module boundaries
2. Preserve chunk metadata
3. Reassemble output
4. Handle cross-chunk types

### Phase 3 Tasks
1. Add refinement pass
2. Generate tests per module
3. Validate integration
4. Report coverage

## Implementation Notes
- Use subagents for parallel work
- Store state in SQLite
- Use MiniMax-M2.7 for transpilation
