"""Prompt templates for transpilation."""

PYTHON_TO_RUST_PROMPT = """You are an expert {source_lang} to {target_lang} developer. Convert this blueprint to idiomatic {target_lang} code.

Blueprint:
```{language}: {source_lang}
{blueprint_content}
```

Requirements:
{target_requirements}

Output ONLY the {target_lang} code, no explanations. If multiple files needed, separate with ---FILE_SEPARATOR--- and include filename as first line like: // filename: lib.ts
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

Output ONLY TypeScript code, no explanations. If multiple files needed, separate with ---FILE_SEPARATOR--- and include filename as first line like: // filename: types.ts
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

Output ONLY Python code, no explanations. If multiple files needed, separate with ---FILE_SEPARATOR--- and include filename as first line like: # filename: models.py
"""

RUST_REQUIREMENTS = """- Use Axum for HTTP handlers if there's an API
- Use Serde for serialization (#[derive(Serialize, Deserialize)])
- Use Tokio for async (#[tokio::main])
- Use Result<T, Box<dyn Error>> or custom error types
- Follow {target_lang} naming conventions (snake_case)
- Add proper error handling with anyhow
- Use async traits if needed (async_trait crate)"""

RUST_TEMPLATE = """// Auto-generated from {source_repo}
// Source: {source_lang} -> Rust

{code}
"""

MAX_FUNCTIONS = 30  # Limit to prevent prompt overflow


def build_transpile_prompt(blueprint: dict, source_lang: str = "python", target_lang: str = "rust") -> str:
    """Build transpilation prompt from blueprint."""
    
    # Get functions and data structures
    funcs = blueprint.get("blueprint", {}).get("functions", [])
    data_structs = blueprint.get("blueprint", {}).get("data_structures", [])
    
    # Limit functions to prevent prompt overflow
    funcs_to_include = funcs[:MAX_FUNCTIONS]
    truncated = len(funcs) > MAX_FUNCTIONS
    
    # Format blueprint content
    content_lines = ["## Functions:"]
    for f in funcs_to_include:
        content_lines.append(f"- {f['name']}: {f['signature']}")
    
    if truncated:
        content_lines.append(f"\n... and {len(funcs) - MAX_FUNCTIONS} more functions (truncated)")
    
    if data_structs:
        content_lines.append("\n## Data Structures:")
        for ds in data_structs:
            content_lines.append(f"- {ds['name']} ({ds.get('type', 'class')})")
            for field in ds.get("fields", []):
                content_lines.append(f"  - {field}")
    
    content = "\n".join(content_lines)
    
    # Route to appropriate prompt based on source -> target
    source_lower = source_lang.lower()
    target_lower = target_lang.lower()
    
    if source_lower in ("javascript", "js") and target_lower in ("typescript", "ts"):
        return JAVASCRIPT_TO_TYPESCRIPT_PROMPT.format(
            blueprint_content=content
        )
    
    if source_lower == "python" and target_lower == "python":
        return PYTHON_TO_PYTHON_PROMPT.format(
            blueprint_content=content
        )
    
    if target_lower == "rust":
        return PYTHON_TO_RUST_PROMPT.format(
            language=source_lang,
            source_lang=source_lang,
            blueprint_content=content,
            target_lang=target_lang,
            target_requirements=RUST_REQUIREMENTS.format(target_lang=target_lang)
        )
    
    # Default fallback
    return f"Convert this {source_lang} blueprint to {target_lang}:\n\n{content}"
