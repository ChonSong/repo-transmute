r"""Prompt templates for transpilation — few-shot examples with safe placeholder escaping."""

from pathlib import Path
from typing import Dict, List, Optional

import yaml


def _esc(s: str) -> str:
    """Escape { braces } that are not template placeholders for str.format()."""
    # Replace bare { with {{  and } with }}  but preserve {blueprint_content}
    return s.replace("{blueprint_content}", "<<BLUEPRINT_PLACEHOLDER>>").replace("{", "{{").replace("}", "}}").replace("<<BLUEPRINT_PLACEHOLDER>>", "{blueprint_content}")


PYTHON_TO_TYPESCRIPT = (
    _esc(r"""You are an expert Python → TypeScript developer. Convert this blueprint to idiomatic TypeScript.

CRITICAL RULES — NON-NEGOTIABLE:

1. PYTHON NONE → TypeScript undefined (NOT null)
   Python:  x = None        → TypeScript:  let x: string | undefined;
   Python:  def foo() -> None  → TypeScript:  function foo(): void | undefined
   NEVER use JavaScript null unless you explicitly mean "no value" in the JS sense.

2. NODE.JS STD LIB IMPORT TABLE — apply whenever you see Python stdlib usage:
   | Python                         | TypeScript (ALWAYS add import)              |
   |-------------------------------|---------------------------------------------|
   | import os; os.path.join()     | import path from "node:path";              |
   | import os; os.path.dirname()  | path.dirname()                              |
   | import os; os.getenv()        | import process from "node:process";         |
   |                                | process.env["KEY"]                           |
   | import os; os.makedirs()      | import fs from "node:fs";                   |
   |                                | await fs.promises.mkdir(dir, {recursive:true})|
   | import json; json.dumps()     | JSON.stringify()  (no import needed)       |
   | import json; json.loads()     | JSON.parse()      (no import needed)       |
   | import datetime; datetime...  | import { Date } from "jsr:@std/datetime";  |
   |                                | OR use native JS Date                        |
   | import re; re.match()         | import { RegExp } from "jsr:@std/regexp";  |
   |                                | OR use native JS /pattern/                   |
   | import uuid; uuid.uuid4()      | import { randomUUID } from "node:crypto";  |
   |                                | crypto.randomUUID()                          |
   | import base64                  | import { Buffer } from "node:buffer";       |
   |                                | Buffer.from(...).toString("base64")          |
   | open(path, "r") / Path(...).read_text() | import fs from "node:fs";  |
   |                                | await fs.promises.readFile(path, "utf-8")    |

   If the blueprint uses any "os", "pathlib", "path", "base64", or "uuid" — you MUST add the corresponding import above.

3. ADD IMPORTS BEFORE ANY USAGE — put all imports at the top of the file, before any function/class definitions.

4. OUTPUT ONLY TypeScript code. NO markdown fences. NO explanations. NO comments outside the code.

5. NO invented imports. Only: built-in JS APIs (JSON, Array, Object, Map, Set, Promise, console, Math, Date, RegExp, URL, fetch, crypto), Node.js built-ins via node: prefix (node:fs, node:path, node:process, node:buffer, node:crypto), or npm packages EXPLICITLY listed in the blueprint imports.

6. Convert Python docstrings to JSDoc format (/** */) on the line ABOVE the declaration.

7. For class methods: output the FULL implementation in TypeScript. NOT just a signature.

8. For standalone functions: output the FULL implementation in TypeScript.

9. NEVER include Python code or Python-like syntax in the output.

FEW-SHOT EXAMPLES:

=== EXAMPLE 1: Python class -> TypeScript class with full method bodies ===

Blueprint source:
# Source imports (use as hints only):
#   import os
#   import json
# Data Structures:
# Config (class)
# Fields:
#   host: str
#   port: int
# Methods:
# # load
# <doc>Load config from a JSON file.</doc>
# def load(cls, path: Path) -> Config:
#     with open(path) as f:
#         data = json.load(f)
#     return cls(host=data["host"], port=data["port"])
# # save
# def save(self, path: Path) -> None:
#     with open(path, "w") as f:
#         json.dump(self.__dict__, f)

Expected output:
""") +
    _esc(r"""// filename: src/Config.ts
import fs from "node:fs";
import path from "node:path";

export interface ConfigData {
  host: string;
  port: number;
}

export class Config implements ConfigData {
  host: string;
  port: number;

  constructor(host: string, port: number) {
    this.host = host;
    this.port = port;
  }

  /** Load config from a JSON file. */
  static async load(filePath: string): Promise<Config> {
    const content = await fs.promises.readFile(filePath, "utf-8");
    const data = JSON.parse(content) as ConfigData;
    return new Config(data.host, data.port);
  }

  /** Save config to a JSON file. */
  async save(filePath: string): Promise<void | undefined> {
    const dir = path.dirname(filePath);
    await fs.promises.mkdir(dir, { recursive: true });
    await fs.promises.writeFile(filePath, JSON.stringify(this, null, 2), "utf-8");
  }
}
=== END EXAMPLE ===

=== EXAMPLE 2: Python standalone function -> TypeScript with full body, path usage ===

Blueprint source:
# Source imports (use as hints only):
#   import os
#   import base64
# Functions (grouped by module):
## utils.py
# # encode_file
# <doc>Encode a file to base64.</doc>
# def encode_file(file_path: str) -> str:
#     with open(file_path, "rb") as f:
#         return base64.b64encode(f.read()).decode()
# # ensure_dir
# <doc>Ensure directory exists.</doc>
# def ensure_dir(dir_path: str) -> None:
#     os.makedirs(dir_path, exist_ok=True)

Expected output:
""") +
    _esc(r"""// filename: src/utils.ts
import fs from "node:fs";
import path from "node:path";
import { Buffer } from "node:buffer";

/** Encode a file to base64. */
export function encodeFile(filePath: string): string {
  const content = fs.readFileSync(filePath);
  return Buffer.from(content).toString("base64");
}

/** Ensure directory exists. */
export function ensureDir(dirPath: string): void | undefined {
  fs.promises.mkdir(dirPath, { recursive: true });
}
=== END EXAMPLE ===

=== EXAMPLE 3: Python function with os.getenv and os.path ===

Blueprint source:
# Source imports (use as hints only):
#   import os
# Functions (grouped by module):
## config.py
# # get_data_dir
# <doc>Get the data directory path.</doc>
# def get_data_dir() -> str:
#     base = os.getenv("DATA_DIR", "/tmp")
#     return os.path.join(base, "myapp")

Expected output:
""") +
    _esc(r"""// filename: src/config.ts
import path from "node:path";
import process from "node:process";

/** Get the data directory path. */
export function getDataDir(): string {
  const base = process.env["DATA_DIR"] ?? "/tmp";
  return path.join(base, "myapp");
}
=== END EXAMPLE ===

Now transpile the following blueprint to TypeScript:

{blueprint_content}
"""))


PYTHON_TO_RUST = r"""You are an expert Python to Rust developer. Convert this blueprint to idiomatic Rust.

CRITICAL RULES:
- Output ONLY Rust code. NO markdown fences. NO explanations.
- Use Axum for HTTP handlers if there's an API.
- Use Serde for serialization (#[derive(Serialize, Deserialize)]).
- Use Tokio for async (#[tokio::main]).
- Use Result<T, Box<dyn Error>> or custom error types.
- Follow Rust naming conventions (snake_case for functions, CamelCase for structs).
- Convert Python docstrings to Rustdoc (///) on the line above items.
- For class methods: output ONLY the method signature + doc. NO implementation body.
- Add proper error handling with anyhow.

Format for multi-file output:
// filename: path/to/file.rs
<content>
---FILE_SEPARATOR---
// filename: path/to/file2.rs
<content>

Blueprint:
{blueprint_content}
"""

PYTHON_TO_GO = """You are an expert Python to Go developer. Convert this blueprint to idiomatic Go.

CRITICAL RULES:
- Output ONLY Go code. NO markdown fences. NO explanations.
- Use proper Go project structure: one package per directory, files start with `package main`.
- Convert Python classes to Go structs with receiver methods.
- Convert Python None -> nil (not null, not undefined).
- Convert Python list/dict -> Go slices/maps with appropriate zero values.
- Use errors with fmt.Errorf and multi-return (func() (T, error)).
- Convert Python type hints to Go type annotations.
- Convert Python docstrings to Go comments (//) on the line above the declaration.
- For struct fields: use JSON tags for serialization: `json:"field_name"`.
- Handle missing imports - Go requires all packages to be imported.
- For HTTP APIs: use net/http or Gin (if third-party packages are listed in imports).
- Follow Go naming conventions: PascalCase for exported names, camelCase for unexported.

FEW-SHOT EXAMPLES:

=== EXAMPLE 1: Python class -> Go struct with methods ===

Blueprint source:
# Source imports (use as hints only):
#   import json
# Data Structures:
# Config (class)
# Fields:
#   host: str
#   port: int
# Methods:
# # load
# <doc>Load config from a JSON file.</doc>
# @classmethod
# def load(cls, path: str) -> Config:
#     with open(path) as f:
#         data = json.load(f)
#     return cls(host=data["host"], port=data["port"])
# # save
# def save(self, path: str) -> None:
#     with open(path, "w") as f:
#         json.dump(self.__dict__, f)

Expected output:
// filename: config.go
package main

import (
	"encoding/json"
	"fmt"
	"os"
)

// Config holds application configuration.
type Config struct {{
	Host string `json:"host"`
	Port int    `json:"port"`
}}

// Load reads a Config from the given JSON file path.
func Load(path string) (*Config, error) {{
	data, err := os.ReadFile(path)
	if err != nil {{
		return nil, fmt.Errorf("reading config file: %w", err)
	}}
	var cfg Config
	if err := json.Unmarshal(data, &cfg); err != nil {{
		return nil, fmt.Errorf("parsing config JSON: %w", err)
	}}
	return &cfg, nil
}}

// Save writes the Config to the given JSON file path.
func (c *Config) Save(path string) error {{
	data, err := json.MarshalIndent(c, "", "  ")
	if err != nil {{
		return fmt.Errorf("marshaling config: %w", err)
	}}
	if err := os.WriteFile(path, data, 0644); err != nil {{
		return fmt.Errorf("writing config file: %w", err)
	}}
	return nil
}}

=== EXAMPLE 2: Python standalone functions -> Go functions ===

Blueprint source:
# Source imports (use as hints only):
#   import os
#   import base64
# Functions (grouped by module):
## utils.py
# # encode_file
# <doc>Encode a file to base64.</doc>
# def encode_file(file_path: str) -> str:
#     with open(file_path, "rb") as f:
#         return base64.b64encode(f.read()).decode()
# # ensure_dir
# <doc>Ensure directory exists.</doc>
# def ensure_dir(dir_path: str) -> None:
#     os.makedirs(dir_path, exist_ok=True)

Expected output:
// filename: utils.go
package main

import (
	"encoding/base64"
	"os"
)

// EncodeFile reads a file and returns its contents as a base64-encoded string.
func EncodeFile(filePath string) (string, error) {{
	data, err := os.ReadFile(filePath)
	if err != nil {{
		return "", fmt.Errorf("reading file: %w", err)
	}}
	return base64.StdEncoding.EncodeToString(data), nil
}}

// EnsureDir creates the directory (and any parents) if it does not exist.
func EnsureDir(dirPath string) error {{
	return os.MkdirAll(dirPath, 0755)
}}

Now transpile the following blueprint to Go:

{{blueprint_content}}
"""

JAVASCRIPT_TO_GO = r"""You are an expert JavaScript/TypeScript to Go developer. Convert this blueprint to idiomatic Go.

CRITICAL RULES:
- Output ONLY Go code. NO markdown fences. NO explanations.
- Use proper Go project structure: one package per directory, files start with `package main`.
- Convert JS undefined / null → nil.
- Convert JS arrays → Go slices ([]T).
- Convert JS objects → Go structs with JSON tags.
- Convert Promises → Go goroutines with error channels or returned errors.
- Use proper Go error handling: multiple return values (func() (T, error)).
- Convert TypeScript types/interfaces → Go struct types with JSON struct tags.
- For HTTP: use net/http or Gin.
- Follow Go naming conventions.

Format for multi-file output:
// filename: path/to/file.go
<content>
---FILE_SEPARATOR---
// filename: path/to/file2.go
<content>

Blueprint:
{blueprint_content}
"""

GO_TO_GO = r"""You are an expert Go developer. Review and improve this Go blueprint with better patterns.

CRITICAL RULES:
- Output ONLY Go code. NO markdown fences. NO explanations.
- Ensure all imports are used.
- Use context.Context for cancellation and timeouts.
- Prefer structured logging (log/slog) over print statements.
- Use errors with fmt.Errorf and %w wrap.
- Add JSON struct tags to all exported struct fields.
- Follow Go idioms and effective Go best practices.

Format for multi-file output:
// filename: path/to/file.go
<content>
---FILE_SEPARATOR---
// filename: path/to/file2.go
<content>

Blueprint:
{blueprint_content}
"""

PYTHON_TO_PYTHON = r"""You are an expert Python developer. Improve this Python blueprint with better patterns.

CRITICAL RULES:
- Output ONLY Python code. NO markdown fences. NO explanations.
- Use type hints throughout.
- Use dataclasses for data structures.
- Convert docstrings to proper docstring format.
- Follow PEP 8.

Format for multi-file output:
// filename: path/to/file.py
<content>
---FILE_SEPARATOR---
// filename: path/to/file2.py
<content>

Blueprint:
{blueprint_content}
"""

TYPESCRIPT_TO_TYPESCRIPT = r"""You are an expert TypeScript developer. Convert this blueprint to idiomatic TypeScript with improved types and patterns.

CRITICAL RULES:
- Output ONLY TypeScript code. NO markdown fences. NO explanations.
- Use strict TypeScript (strict mode, no implicit any).
- Add proper type annotations throughout.
- Add interfaces for all data structures.
- Convert docstrings to JSDoc (/** */) on the line ABOVE declarations.
- For class methods: output ONLY the method signature + JSDoc. NO implementation body.
- Follow TypeScript naming conventions.

Format for multi-file output:
// filename: path/to/file.ts
<content>
---FILE_SEPARATOR---
// filename: path/to/file2.ts
<content>

Blueprint:
{blueprint_content}
"""

JAVASCRIPT_TO_TYPESCRIPT = r"""You are an expert JavaScript to TypeScript developer. Convert this blueprint to idiomatic TypeScript.

CRITICAL RULES:
- Output ONLY TypeScript code. NO markdown fences. NO explanations.
- Use TypeScript best practices (strict mode).
- Add proper type annotations.
- Use interfaces for data structures.
- Convert docstrings to JSDoc.
- For class methods: output ONLY the method signature + JSDoc. NO implementation body.

Format for multi-file output:
// filename: path/to/file.ts
<content>
---FILE_SEPARATOR---
// filename: path/to/file2.ts
<content>

Blueprint:
{blueprint_content}
"""

TSX_TEMPLATE = r"""You are an expert React/TypeScript developer. Convert this blueprint to idiomatic TSX/React components.

CRITICAL RULES:
- Output ONLY TSX/TypeScript code. NO markdown fences. NO explanations.
- Use functional components with hooks (React 18+).
- Type all props with interfaces.
- Convert docstrings to JSDoc.
- Handle loading, error, and empty states.

Format for multi-file output:
// filename: path/to/Component.tsx
<content>
---FILE_SEPARATOR---
// filename: path/to/file2.ts
<content>

Blueprint:
{blueprint_content}
"""

MAX_FUNCTIONS = 30


def _format_function(f: dict) -> str:
    """Format a function for the prompt. Body already contains the full def line."""
    parts = [f"# {f['name']}"]
    if f.get("docstring"):
        parts.append(f'<doc>{f["docstring"][:300]}</doc>')
    if f.get("body"):
        parts.append(f["body"])
    return "\n".join(parts)


def _format_data_structure(ds: dict) -> str:
    """Format a data structure for the prompt."""
    parts = [f"# {ds['name']} ({ds.get('type', 'class')})"]
    if ds.get("fields"):
        parts.append("# Fields:")
        for field in ds["fields"]:
            parts.append(f"#   {field}")
    if ds.get("methods"):
        for m in ds["methods"]:
            parts.append(_format_function(m))
    return "\n".join(parts)


def _group_by_file(funcs: list) -> dict[str, list]:
    """Group functions by file path."""
    groups: dict[str, list] = {}
    for f in funcs:
        file_path = f.get("file", "")
        if "/" in file_path:
            module = "/".join(file_path.rsplit("/", 2)[-2:])
        else:
            module = file_path or "root"
        groups.setdefault(module, []).append(f)
    return groups


def format_cross_chunk_context(
    cross_chunk_exports: List[Dict[str, object]],
    target_lang: str = "typescript",
) -> str:
    """Format cross-chunk export information as prompt context.

    When transpiling chunk N, this provides the LLM with information
    about symbols exported by previously-transpiled chunks (chunks 0..N-1)
    and the output file paths where those symbols can be imported from.

    Args:
        cross_chunk_exports: List of dicts, each with:
            - "file": str — output file path (e.g. "src/utils.ts")
            - "exports": list[str] — exported symbol names
            - "functions": list[dict] — (optional) function signatures
            - "data_structures": list[dict] — (optional) class/struct names
        target_lang: Target language (affects import syntax in example).

    Returns:
        Formatted string to include in the prompt, or empty string if
        cross_chunk_exports is empty.
    """
    if not cross_chunk_exports:
        return ""

    lines: list[str] = []

    if target_lang.lower() in ("typescript", "ts", "javascript", "js", "tsx"):
        lines.append("# CROSS-CHUNK CONTEXT — symbols already transpiled in other chunks:")
        lines.append("# When you need a symbol listed below, import it from the shown file path.")
        lines.append("# Example: import { SymbolName } from \"./path/to/file\";")
        lines.append("")
    elif target_lang.lower() == "go":
        lines.append("# CROSS-CHUNK CONTEXT — symbols already transpiled in other chunks:")
        lines.append("# These symbols are already defined in other Go files in the same package.")
        lines.append("# Do NOT re-define them. Reference them directly (same-package access).")
        lines.append("")
    elif target_lang.lower() == "rust":
        lines.append("# CROSS-CHUNK CONTEXT — symbols already transpiled in other chunks:")
        lines.append("# These symbols are available via crate-level use statements.")
        lines.append("# Example: use crate::module::SymbolName;")
        lines.append("")
    elif target_lang.lower() == "python":
        lines.append("# CROSS-CHUNK CONTEXT — symbols already transpiled in other chunks:")
        lines.append("# When you need a symbol listed below, import it from the shown module path.")
        lines.append("# Example: from module.path import SymbolName")
        lines.append("")
    else:
        lines.append("# CROSS-CHUNK CONTEXT — symbols already transpiled in other chunks:")
        lines.append("")

    for chunk_info in cross_chunk_exports:
        filepath = chunk_info.get("file", "unknown")
        exports = chunk_info.get("exports", [])

        lines.append(f"# File: {filepath}")

        # Format function signatures if available
        functions = chunk_info.get("functions", [])
        data_structures = chunk_info.get("data_structures", [])

        if functions:
            for func in functions:
                name = func.get("name", "?")
                sig = func.get("signature", "")
                if sig:
                    lines.append(f"#   - {name}: {sig}")
                else:
                    lines.append(f"#   - {name}")

        if data_structures:
            for ds in data_structures:
                name = ds.get("name", "?")
                ds_type = ds.get("type", "class")
                fields = ds.get("fields", [])
                if fields:
                    field_str = ", ".join(
                        f if isinstance(f, str) else str(f)
                        for f in fields[:5]
                    )
                    lines.append(f"#   - {name} ({ds_type}): {field_str}")
                else:
                    lines.append(f"#   - {name} ({ds_type})")

        # If no detailed info, just list export names
        if not functions and not data_structures and exports:
            lines.append(f"#   Exports: {', '.join(str(e) for e in exports)}")

        lines.append("")

    return "\n".join(lines)


def build_transpile_prompt(
    blueprint: dict,
    source_lang: str = "python",
    target_lang: str = "typescript",
    cross_chunk_exports: Optional[List[Dict[str, object]]] = None,
) -> str:
    """
    Build a transpilation prompt from a blueprint dict.
    Includes FULL function bodies, grouped by module.

    Args:
        blueprint: Blueprint dict with 'blueprint' key containing
            functions, data_structures, etc.
        source_lang: Source language of the code.
        target_lang: Target language to transpile to.
        cross_chunk_exports: Optional list of export info from previously-
            transpiled chunks. Each entry is a dict with 'file', 'exports',
            and optionally 'functions' and 'data_structures'. When provided,
            this context is prepended so the LLM knows what symbols are
            already available and can generate correct import statements.
    """
    funcs = blueprint.get("blueprint", {}).get("functions", [])
    data_structs = blueprint.get("blueprint", {}).get("data_structures", [])
    source_files = [f.get("file", "") for f in funcs]
    has_tsx = any(f.endswith(".tsx") for f in source_files)

    funcs_to_include = funcs[:MAX_FUNCTIONS]
    truncated = len(funcs) > MAX_FUNCTIONS

    content_parts: list[str] = []

    # Cross-chunk context: tell the LLM what other chunks have already exported
    if cross_chunk_exports:
        ctx = format_cross_chunk_context(cross_chunk_exports, target_lang)
        if ctx:
            content_parts.append(ctx)

    imports = blueprint.get("blueprint", {}).get("imports", [])
    if imports and source_lang == "python":
        content_parts.append("# Source imports (use as hints only, do NOT blindly import):")
        for imp in imports[:20]:
            if isinstance(imp, dict):
                content_parts.append(f"#   import {imp.get('module', '')}")
            else:
                content_parts.append(f"#   import {imp}")
        content_parts.append("")

    if data_structs:
        content_parts.append("# Data Structures:")
        for ds in data_structs:
            content_parts.append(_format_data_structure(ds))
        content_parts.append("")

    content_parts.append("# Functions (grouped by module):")
    grouped = _group_by_file(funcs_to_include)
    for module, module_funcs in sorted(grouped.items()):
        content_parts.append(f"\n## {module}")
        for f in module_funcs:
            content_parts.append(_format_function(f))
        content_parts.append("")

    if truncated:
        content_parts.append(f"# ... and {len(funcs) - MAX_FUNCTIONS} more functions (truncated)")

    content = "\n".join(content_parts)

    source_lower = source_lang.lower()
    target_lower = target_lang.lower()

    if source_lower == "python" and target_lower in ("typescript", "ts"):
        if has_tsx:
            return TSX_TEMPLATE.format(blueprint_content=content)
        return PYTHON_TO_TYPESCRIPT.format(blueprint_content=content)

    if source_lower == "python" and target_lower == "python":
        return PYTHON_TO_PYTHON.format(blueprint_content=content)

    if source_lower == "python" and target_lower == "rust":
        return PYTHON_TO_RUST.format(blueprint_content=content)

    if source_lower == "python" and target_lower == "go":
        return PYTHON_TO_GO.format(blueprint_content=content)

    if source_lower in ("typescript", "ts") and target_lower in ("typescript", "ts"):
        if has_tsx:
            return TSX_TEMPLATE.format(blueprint_content=content)
        return TYPESCRIPT_TO_TYPESCRIPT.format(blueprint_content=content)

    if source_lower in ("javascript", "js"):
        if target_lower == "go":
            return JAVASCRIPT_TO_GO.format(blueprint_content=content)
        return JAVASCRIPT_TO_TYPESCRIPT.format(blueprint_content=content)

    if source_lower == "go" and target_lower == "go":
        return GO_TO_GO.format(blueprint_content=content)

    return f"Convert this {source_lang} code to {target_lang}:\n\n{content}"
