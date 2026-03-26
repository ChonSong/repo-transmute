"""Prompt templates for transpilation — includes full function bodies."""

PYTHON_TO_TYPESCRIPT_PROMPT = """You are an expert Python → TypeScript developer. Convert this blueprint to idiomatic TypeScript.

CRITICAL RULES:
- Output ONLY TypeScript code. NO markdown fences. NO explanations. NO comments outside the code.
- NO invented imports. Use only: built-in JS APIs (JSON.parse/string, Array.from/map/filter/reduce, Object.keys/values/entries, Map, Set, Promise, console, Math, Date, RegExp, URL, fetch), or npm packages that are EXPLICITLY listed in the blueprint imports.
- DO NOT import from "async", "json", "regex", "system", "os", "path" as npm packages.
- For file path operations use the browser/Node.js built-ins or explicit package names.
- For async, use native Promise/async-await only — NOT a package named "async".
- Convert Python docstrings to JSDoc format (/** */) on the line ABOVE the declaration.
- For class methods: output ONLY the method signature + JSDoc. NO implementation body.
- For standalone functions: output the full implementation translated to TypeScript.
- NEVER include Python code or Python-like syntax in the output.
- If unsure about an import, OMIT it rather than inventing it.

Format for multi-file output:
// filename: path/to/file.ts
<content>
---FILE_SEPARATOR---
// filename: path/to/file2.ts
<content>

Blueprint:
{blueprint_content}
"""

PYTHON_TO_RUST_PROMPT = """You are an expert Python to Rust developer. Convert this blueprint to idiomatic Rust.

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

PYTHON_TO_PYTHON_PROMPT = """You are an expert Python developer. Improve this Python blueprint with better patterns.

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

TYPESCRIPT_TO_TYPESCRIPT_PROMPT = """You are an expert TypeScript developer. Convert this blueprint to idiomatic TypeScript with improved types and patterns.

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

JAVASCRIPT_TO_TYPESCRIPT_PROMPT = """You are an expert JavaScript to TypeScript developer. Convert this blueprint to idiomatic TypeScript.

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

TSX_TEMPLATE = """You are an expert React/TypeScript developer. Convert this blueprint to idiomatic TSX/React components.

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
        parts.append(f'"""{f["docstring"][:300]}"""')
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


def build_transpile_prompt(
    blueprint: dict, source_lang: str = "python", target_lang: str = "typescript"
) -> str:
    """
    Build a transpilation prompt from a blueprint dict.

    Includes FULL function bodies, grouped by module.
    Selects the right template based on source + target language pair.
    """
    funcs = blueprint.get("blueprint", {}).get("functions", [])
    data_structs = blueprint.get("blueprint", {}).get("data_structures", [])
    source_files = [f.get("file", "") for f in funcs]
    has_tsx = any(f.endswith(".tsx") for f in source_files)

    funcs_to_include = funcs[:MAX_FUNCTIONS]
    truncated = len(funcs) > MAX_FUNCTIONS

    content_parts: list[str] = []

    # Include source imports as hints (for validity checking)
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
        return PYTHON_TO_TYPESCRIPT_PROMPT.format(blueprint_content=content)

    if source_lower == "python" and target_lower == "python":
        return PYTHON_TO_PYTHON_PROMPT.format(blueprint_content=content)

    if source_lower == "python" and target_lower == "rust":
        return PYTHON_TO_RUST_PROMPT.format(blueprint_content=content)

    if source_lower in ("typescript", "ts") and target_lower in ("typescript", "ts"):
        if has_tsx:
            return TSX_TEMPLATE.format(blueprint_content=content)
        return TYPESCRIPT_TO_TYPESCRIPT_PROMPT.format(blueprint_content=content)

    if source_lower in ("javascript", "js"):
        return JAVASCRIPT_TO_TYPESCRIPT_PROMPT.format(blueprint_content=content)

    return f"Convert this {source_lang} code to {target_lang}:\n\n{content}"
