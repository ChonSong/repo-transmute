# Go Support for RepoTransmute — Implementation Brief

## Overview

Add Go language support to RepoTransmute: extract functions, structs, and interfaces from Go source files and use them in the blueprint/transpilation pipeline.

## Architecture

Go's AST lives in `go/ast` (part of the Go stdlib). Since Python can't parse Go natively, the approach is:
1. A **tiny Go helper binary** (`scripts/goast/`) uses `go/ast` + `go/parser` to emit JSON
2. Python's `extract_from_go()` calls this binary as a subprocess
3. Output is parsed as JSON and converted to RepoTransmute's `Function`/`DataStructure` types

```
Go source file
    → goast (subprocess) → JSON
    → extract_from_go()  → List[Function], List[DataStructure]
    → Blueprint
```

## Files to Create/Modify

### 1. `scripts/goast/main.go` (NEW)
A standalone Go program that:
- Takes a `.go` file path as argument
- Parses it with `go/ast` and `go/parser`
- Emits JSON to stdout: `{ "functions": [...], "structs": [...], "interfaces": [...] }`
- Handles its own errors gracefully (malformed Go → empty JSON with error to stderr)

**Key structs to extract:**
- `FuncDecl` → `name`, `type` (signature), `pos` (line number)
- `StructType` fields → `name`, `fields` (field names + types)
- `InterfaceType` methods → `name`, method signatures

### 2. `src/repo_transmute/transpiler/go_parser.py` (NEW)
Python module with:
- `extract_from_go(file_path: Path) -> List[Function]` — calls goast, maps JSON → Function dataclasses
- `extract_structs_from_go(file_path: Path) -> List[DataStructure]`
- `extract_interfaces_from_go(file_path: Path) -> List[DataStructure]`
- `parse_goast_output(json_text: str)` — JSON deserializer

### 3. `src/repo_transmute/blueprint/extractor.py` (MODIFY)
- Add `"go"` to `lang_exts`: `lang_exts["go"] = {".go"}`
- Add Go to `extractors` dict: `"go": (extract_from_go, extract_structs_from_go)`
- Call `extract_structs_from_go` (for structs and interfaces) alongside functions

### 4. `tests/test_go_parser.py` (NEW)
Tests covering:
- Happy path: parse a real `.go` file, verify functions and structs extracted
- goast binary not found → graceful error
- Malformed JSON from goast → handle gracefully
- Struct with multiple fields
- Interface with multiple methods
- Package-level doc comments

### 5. `src/repo_transmute/transpiler/compatibility.py` (VERIFY)
- Already has `Language.GO` and `TargetLanguage.GO` ✓
- Already has routing: `Language.GO → (TargetLanguage.GO, 0.85, ...)` ✓
- No changes needed

### 6. `src/repo_transmute/transpiler/validate.py` (VERIFY)
- Already has `validate_go()` using `go build -o /dev/null` ✓
- No changes needed

## Data Format (goast → Python)

goast outputs JSON like:
```json
{
  "functions": [
    {
      "name": "Add",
      "signature": "(a int, b int) int",
      "line": 4,
      "doc": "Add returns the sum of two integers.",
      "is_method": false,
      "receiver": ""
    }
  ],
  "structs": [
    {
      "name": "Person",
      "line": 10,
      "doc": "Person represents a human being.",
      "fields": [
        {"name": "Name", "type": "string"},
        {"name": "Age", "type": "int"}
      ]
    }
  ],
  "interfaces": [
    {
      "name": "Reader",
      "line": 20,
      "doc": "Reader is an interface for reading data.",
      "methods": [
        {"name": "Read", "signature": "(p []byte) (n int, err error)"}
      ]
    }
  ]
}
```

Python maps to:
- `Function` (from `extractor.py`)
- `DataStructure(type="struct", ...)` and `DataStructure(type="interface", ...)`

## Test Fixture

Create a sample Go file at `tests/fixtures/sample.go`:
```go
// Package fixtures is a test package.
package fixtures

import "fmt"

// Add returns the sum of two integers.
func Add(a int, b int) int {
    return a + b
}

// Person represents a human being.
type Person struct {
    Name string
    Age  int
}

// Reader is an interface for reading data.
type Reader interface {
    Read(p []byte) (n int, err error)
}
```

## Constraints

- Go binary is already installed (`go1.22.2`). `goast` binary must be buildable via `go build -o goast main.go`
- The `goast` binary should be a single file, no external dependencies beyond stdlib
- The Python code must handle the case where `goast` binary is not found or fails
- All existing tests must continue to pass

## Running Tests

```bash
cd repo-transmute
python -m pytest tests/test_go_parser.py -v

# Build goast manually (for local testing)
cd scripts/goast && go build -o goast main.go && cd ../..
```
