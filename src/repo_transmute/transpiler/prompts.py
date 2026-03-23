"""Prompt templates for transpilation — includes full function bodies."""

PYTHON_TO_TYPESCRIPT_PROMPT = """You are an expert Python → TypeScript developer. Convert this blueprint to idiomatic TypeScript.

Blueprint:
```python
{blueprint_content}
```

Requirements:
- Use TypeScript best practices (strict mode, no 'any')
- Add proper type annotations — infer from Python hints where possible
- Map Python types: str→string, int/float→number, bool→boolean, list→any[], dict→Record<string, any>, None→null
- Convert async def → async function, def → function
- Use interfaces for data structures
- Add JSDoc comments from docstrings
- Follow TypeScript naming conventions (camelCase for vars/functions, PascalCase for classes/interfaces)
- Use proper error handling (try/catch)
- Preserve module/file grouping

Output ONLY TypeScript code, no explanations.
If multiple files needed, separate with ---FILE_SEPARATOR--- and include filename as first line like: // filename: agent/loop.ts
"""

PYTHON_TO_RUST_PROMPT = """You are an expert Python to Rust developer. Convert this blueprint to idiomatic Rust.

Blueprint:
```python
{blueprint_content}
```

Requirements:
- Use Axum for HTTP handlers if there's an API
- Use Serde for serialization (#[derive(Serialize, Deserialize)])
- Use Tokio for async (#[tokio::main])
- Use Result<T, Box<dyn Error>> or custom error types
- Follow Rust naming conventions (snake_case for functions, CamelCase for structs)
- Add proper error handling with anyhow
- Use async traits if needed (async_trait crate)

Output ONLY Rust code, no explanations.
If multiple files needed, separate with ---FILE_SEPARATOR--- and include filename as first line.
"""

PYTHON_TO_PYTHON_PROMPT = """You are an expert Python developer. Improve this Python blueprint with better patterns.

Blueprint:
```python
{blueprint_content}
```

Requirements:
- Use type hints throughout
- Use dataclasses for data structures
- Add docstrings
- Follow PEP 8
- Use async/await where appropriate
- Add proper error handling

Output ONLY Python code, no explanations.
If multiple files needed, separate with ---FILE_SEPARATOR--- and include filename as first line.
"""

# TypeScript/JavaScript transpilation — handles TS, TSX, JS, JSX
TYPESCRIPT_TO_TYPESCRIPT_PROMPT = """You are an expert TypeScript developer. Convert this blueprint to idiomatic TypeScript with improved types and patterns.

Blueprint:
```typescript
{blueprint_content}
```

Requirements:
- Use strict TypeScript (strict mode, no implicit any)
- Add proper type annotations throughout
- Add interfaces for all data structures
- Add JSDoc comments for all exported functions
- Follow TypeScript naming conventions
- Preserve React/JSX if present (keep .tsx files as JSX)
- Use proper error handling
- Add null checks

Output ONLY TypeScript code, no explanations.
If multiple files needed, separate with ---FILE_SEPARATOR--- and include filename as first line.
"""

JAVASCRIPT_TO_TYPESCRIPT_PROMPT = """You are an expert JavaScript to TypeScript developer. Convert this blueprint to idiomatic TypeScript.

Blueprint:
```javascript
{blueprint_content}
```

Requirements:
- Use TypeScript best practices (strict mode)
- Add proper type annotations
- Use interfaces for data structures
- Use async/await properly
- Follow TypeScript naming conventions
- Add JSDoc comments for documentation
- Use proper error handling

Output ONLY TypeScript code, no explanations.
If multiple files needed, separate with ---FILE_SEPARATOR--- and include filename as first line.
"""

# TSX / React component template
TSX_TEMPLATE = """You are an expert React/TypeScript developer. Convert this blueprint to idiomatic TSX/React components.

Blueprint:
```typescript
{blueprint_content}
```

Requirements:
- Use functional components with hooks (React 18+)
- Type all props with interfaces
- Handle loading, error, and empty states
- Use proper TypeScript for async data fetching
- Keep components small and focused
- Use CSS classes or inline styles for layout

Output ONLY TSX/TypeScript code, no explanations.
If multiple files needed, separate with ---FILE_SEPARATOR--- and include filename as first line like: // filename: components/AgentPanel.tsx
"""

MAX_FUNCTIONS = 30  # Limit per prompt chunk


def _format_function(f: dict) -> str:
    """Format a function for the prompt. Body already contains the full def line."""
    parts = [f"# {f['name']}"]
    if f.get("docstring"):
        parts.append(f'"""{f["docstring"][:200]}"""')
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

    # Python → TypeScript
    if source_lower == "python" and target_lower in ("typescript", "ts"):
        if has_tsx:
            return TSX_TEMPLATE.format(blueprint_content=content)
        return PYTHON_TO_TYPESCRIPT_PROMPT.format(blueprint_content=content)

    # Python → Python (improve patterns)
    if source_lower == "python" and target_lower == "python":
        return PYTHON_TO_PYTHON_PROMPT.format(blueprint_content=content)

    # Python → Rust
    if source_lower == "python" and target_lower == "rust":
        return PYTHON_TO_RUST_PROMPT.format(
            blueprint_content=content, source_lang=source_lang, target_lang=target_lang
        )

    # TypeScript → TypeScript (type improvement / re-typing)
    if source_lower in ("typescript", "ts") and target_lower in ("typescript", "ts"):
        if has_tsx:
            return TSX_TEMPLATE.format(blueprint_content=content)
        return TYPESCRIPT_TO_TYPESCRIPT_PROMPT.format(blueprint_content=content)

    # JavaScript → TypeScript
    if source_lower in ("javascript", "js"):
        return JAVASCRIPT_TO_TYPESCRIPT_PROMPT.format(blueprint_content=content)

    # Final fallback
    return f"Convert this {source_lang} code to {target_lang}:\n\n{content}"
