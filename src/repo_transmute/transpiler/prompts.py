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


# ═══════════════════════════════════════════════════════════════════
# Frontend Migration Prompts
# ═══════════════════════════════════════════════════════════════════

REACT_COMPONENT_MIGRATION_PROMPT = """You are an expert React/TypeScript developer migrating components between projects.

## Source Component Blueprint

```yaml
name: {component_name}
file: {component_file}
props: {props}
state_count: {state_count}
children: {children}
hooks: {hooks}
css_approach: {css_approach}
tailwind_classes_count: {tailwind_count}
theme_vars_used: {theme_vars}
```

## Source Component Code

```tsx
{source_code}
```

## Migration Requirements

### API Mapping
The following API URLs need to be rewritten:
{api_mappings}

### Theme System
- Source uses: {source_theme_approach}
- Target uses: {target_theme_approach}
- Theme variables to map: {theme_mapping}

### Specific Changes Required
{specific_changes}

### General Rules
- Keep the same component behavior and props interface
- Update API calls to use the target project's endpoints
- Adapt CSS/theme references to match the target project's theme system
- Use the target project's component library and utility patterns
- Preserve all accessibility attributes
- Keep TypeScript types strict
- Output valid TSX that compiles with the target project's tsconfig

Output ONLY the migrated TSX code, no explanations. Include the filename as the first comment line: // filename: ComponentName.tsx
"""

CSS_THEME_MIGRATION_PROMPT = """You are an expert CSS/Tailwind developer migrating theme systems between projects.

## Source Theme System
{source_theme_description}

## Target Theme System  
{target_theme_description}

## Source CSS File
```css
{source_css}
```

## Migration Requirements

### Variable Mapping
Map these source variables to target equivalents:
{variable_mapping}

### Rules
- Preserve all keyframe animations and utility classes
- Convert theme variable references to the target format
- If target uses Tailwind v4, convert CSS variables to @theme directives
- Keep the same visual design intent
- Maintain responsive breakpoints
- Preserve dark/light mode variants

Output ONLY the migrated CSS, no explanations.
"""

API_REWRITE_PROMPT = """You are an expert React developer rewriting API calls for a different backend.

## Current API Calls
{current_api_calls}

## Target API Contract
{target_api_contract}

## Rewrite Rules
{rewrite_rules}

## Requirements
- Rewrite each API call to use the target endpoint
- Preserve the same request/response handling logic
- Maintain SSE streaming behavior if present
- Keep error handling patterns
- Update any response type parsing

Output ONLY the updated TypeScript code with rewritten API calls.
"""


def build_frontend_migration_prompt(
    component_blueprint: dict,
    source_code: str,
    api_mappings: str,
    theme_mapping: str,
    specific_changes: str,
    source_theme_approach: str,
    target_theme_approach: str,
) -> str:
    """Build a frontend component migration prompt."""
    return REACT_COMPONENT_MIGRATION_PROMPT.format(
        component_name=component_blueprint.get('name', 'Unknown'),
        component_file=component_blueprint.get('file', ''),
        props=str(component_blueprint.get('props', [])),
        state_count=component_blueprint.get('state_count', 0),
        children=str(component_blueprint.get('children', [])),
        hooks=str(component_blueprint.get('hooks', [])),
        css_approach=component_blueprint.get('css_approach', 'unknown'),
        tailwind_count=component_blueprint.get('tailwind_classes_count', 0),
        theme_vars=str(component_blueprint.get('theme_vars_used', [])),
        source_code=source_code,
        api_mappings=api_mappings,
        theme_mapping=theme_mapping,
        specific_changes=specific_changes,
        source_theme_approach=source_theme_approach,
        target_theme_approach=target_theme_approach,
    )
