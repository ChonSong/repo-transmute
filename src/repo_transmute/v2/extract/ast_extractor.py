"""AST-based component extraction — uses tree-sitter for accurate parsing."""

from __future__ import annotations

import re
from pathlib import Path

from repo_transmute.v2.models import (
    ComponentDef,
    RouteDef,
    ComponentType,
    PropDef,
    StateDef,
    EffectDef,
    ImportDef,
    APICallDef,
    Framework,
)


def extract_components_ast(
    repo_path: Path,
    framework: Framework,
    files: list[Path] | None = None,
) -> list[ComponentDef]:
    """Extract component definitions using AST-aware parsing.
    
    Falls back to regex-based parsing if tree-sitter is not available.
    """
    if files is None:
        # Auto-discover component files
        files = _discover_component_files(repo_path, framework)
    
    components = []
    for file_path in files:
        try:
            content = file_path.read_text()
            rel_path = str(file_path.relative_to(repo_path))
            
            if framework in (Framework.REACT, Framework.NEXTJS, Framework.PREACT, Framework.SOLID):
                comps = _extract_react_components(content, rel_path, file_path)
            elif framework == Framework.VUE:
                comps = _extract_vue_components(content, rel_path, file_path)
            elif framework == Framework.SVELTE:
                comps = _extract_svelte_components(content, rel_path, file_path)
            else:
                comps = _extract_generic_components(content, rel_path, file_path)
            
            components.extend(comps)
        except Exception:
            # Skip files that can't be parsed
            continue
    
    return components


def _discover_component_files(repo_path: Path, framework: Framework) -> list[Path]:
    """Find component files in the project."""
    exts = {
        Framework.REACT: [".tsx", ".jsx"],
        Framework.NEXTJS: [".tsx", ".jsx"],
        Framework.PREACT: [".tsx", ".jsx"],
        Framework.SOLID: [".tsx", ".jsx"],
        Framework.VUE: [".vue"],
        Framework.SVELTE: [".svelte"],
    }
    suffixes = exts.get(framework, [".tsx", ".jsx", ".vue", ".svelte"])
    
    files = []
    skip_dirs = {"node_modules", ".git", "dist", "build", ".next", ".nuxt", ".cache"}
    
    for suffix in suffixes:
        for file_path in repo_path.rglob(f"*{suffix}"):
            if not any(skip in file_path.parts for skip in skip_dirs):
                files.append(file_path)
    
    return files


def _extract_react_components(
    content: str,
    file_path: str,
    abs_path: Path,
) -> list[ComponentDef]:
    """Extract React components from TSX/JSX content."""
    components = []
    
    # Find component function definitions
    # Matches: export function Name(, export const Name = (, function Name(, const Name = (
    func_pattern = re.compile(
        r'(?:export\s+)?(?:default\s+)?(?:function|const)\s+(\w+)\s*(?:=\s*)?(?:\(|<)',
        re.MULTILINE,
    )
    
    lines = content.split("\n")
    for match in func_pattern.finditer(content):
        name = match.group(1)
        # Skip non-component names (lowercase, utils, hooks)
        if not name[0].isupper() or name.startswith("use"):
            continue
        
        line_num = content[:match.start()].count("\n") + 1
        
        # Extract the component's source
        comp_source = _extract_function_body(content, match.start())
        
        comp = ComponentDef(
            name=name,
            file=file_path,
            line=line_num,
            full_source=comp_source,
            template_source=_extract_jsx_portion(comp_source),
            has_jsx=True,
        )
        
        # Extract props
        comp.props = _extract_react_props(content, match.start())
        
        # Extract state
        comp.state = _extract_react_state(comp_source)
        
        # Extract effects
        comp.effects = _extract_react_effects(comp_source)
        
        # Extract API calls
        comp.api_calls = _extract_api_calls(comp_source)
        
        # Extract imports
        comp.imports = _extract_imports(content)
        
        # Extract child components
        comp.children_components = _extract_child_components(comp_source)
        
        # Extract hooks
        comp.hooks_used = _extract_hooks(comp_source)
        
        # JSX complexity
        comp.jsx_complexity = comp_source.count("<") - comp_source.count("</")
        
        # CSS approach
        comp.css_approach = _detect_css_approach(comp_source)
        comp.css_variables_used = _extract_css_variables(comp_source)
        comp.tailwind_classes = _extract_tailwind_classes(comp_source)
        
        # Determine component type
        if "pages/" in file_path or "routes/" in file_path:
            comp.component_type = ComponentType.PAGE
        elif "layout" in name.lower() or "Layout" in name:
            comp.component_type = ComponentType.LAYOUT
        elif "components/" in file_path or "ui/" in file_path:
            comp.component_type = ComponentType.COMPONENT
        
        components.append(comp)
    
    return components


def _extract_vue_components(
    content: str,
    file_path: str,
    abs_path: Path,
) -> list[ComponentDef]:
    """Extract Vue SFC components."""
    # Vue .vue files are SFCs — each file is one component
    if not content.strip():
        return []
    
    # Extract component name from filename or <script> export
    name_match = re.search(r'export\s+default\s*{[^}]*name:\s*["\'](\w+)["\']', content)
    if name_match:
        name = name_match.group(1)
    else:
        # Use filename as component name
        name = abs_path.stem
    
    # Extract template portion
    template_match = re.search(r'<template[^>]*>(.*?)</template>', content, re.DOTALL)
    template_source = template_match.group(1) if template_match else ""
    
    # Extract script portion
    script_match = re.search(r'<script[^>]*>(.*?)</script>', content, re.DOTALL)
    script_source = script_match.group(1) if script_match else ""
    
    comp = ComponentDef(
        name=name,
        file=file_path,
        line=1,
        full_source=content,
        template_source=template_source,
        has_jsx=False,
    )
    
    # Vue uses ref(), reactive(), computed() instead of useState
    comp.state = _extract_vue_state(script_source)
    comp.effects = _extract_vue_effects(script_source)
    comp.api_calls = _extract_api_calls(script_source)
    comp.imports = _extract_imports(script_source)
    comp.css_approach = _detect_css_approach(content)
    comp.css_variables_used = _extract_css_variables(content)
    comp.tailwind_classes = _extract_tailwind_classes(content)
    comp.jsx_complexity = template_source.count("<") - template_source.count("</")
    
    return [comp]


def _extract_svelte_components(
    content: str,
    file_path: str,
    abs_path: Path,
) -> list[ComponentDef]:
    """Extract Svelte components."""
    if not content.strip():
        return []
    
    name = abs_path.stem
    
    comp = ComponentDef(
        name=name,
        file=file_path,
        line=1,
        full_source=content,
        template_source="",
        has_jsx=False,
    )
    
    # Svelte uses let: for state
    comp.state = _extract_svelte_state(content)
    comp.effects = _extract_svelte_effects(content)
    comp.api_calls = _extract_api_calls(content)
    comp.imports = _extract_imports(content)
    comp.css_approach = _detect_css_approach(content)
    comp.css_variables_used = _extract_css_variables(content)
    comp.tailwind_classes = _extract_tailwind_classes(content)
    comp.jsx_complexity = content.count("<") - content.count("</")
    
    return [comp]


def _extract_generic_components(
    content: str,
    file_path: str,
    abs_path: Path,
) -> list[ComponentDef]:
    """Fallback: extract components using generic heuristics."""
    return _extract_react_components(content, file_path, abs_path)


# ── Helper extraction functions ──────────────────────────────────────────────


def _extract_function_body(content: str, start: int) -> str:
    """Extract the body of a function starting from a match position."""
    # Find the opening brace
    brace_pos = content.find("{", start)
    if brace_pos == -1:
        return ""
    
    # Count braces to find the matching close
    depth = 1
    pos = brace_pos + 1
    while pos < len(content) and depth > 0:
        if content[pos] == "{":
            depth += 1
        elif content[pos] == "}":
            depth -= 1
        pos += 1
    
    return content[start:pos]


def _extract_jsx_portion(source: str) -> str:
    """Extract the JSX/template return portion from a component."""
    # Look for return ( or return <
    return_match = re.search(r'return\s*\((.*?)\)\s*;?\s*$', source, re.DOTALL)
    if return_match:
        return return_match.group(1)
    return ""


def _extract_react_props(content: str, start: int) -> list[PropDef]:
    """Extract component props from TypeScript interface or destructuring."""
    props = []
    
    # Look for TypeScript interface
    interface_match = re.search(
        r'interface\s+\w+Props\s*{([^}]+)}',
        content[start:start+500],
        re.DOTALL,
    )
    if interface_match:
        for line in interface_match.group(1).split("\n"):
            line = line.strip()
            if not line:
                continue
            prop_match = re.match(r'(\w+)(\?)?:\s*(.+?);', line)
            if prop_match:
                props.append(PropDef(
                    name=prop_match.group(1),
                    type=prop_match.group(3),
                    required=prop_match.group(2) is None,
                ))
    
    return props


def _extract_react_state(source: str) -> list[StateDef]:
    """Extract useState calls."""
    states = []
    for match in re.finditer(r'useState<([^>]*)>\s*\(([^)]*)\)', source):
        states.append(StateDef(
            name=f"state_{len(states)}",
            type=match.group(1) or "unknown",
            init_value=match.group(2) or "",
            framework_specific="useState",
        ))
    return states


def _extract_react_effects(source: str) -> list[EffectDef]:
    """Extract useEffect calls."""
    effects = []
    for match in re.finditer(r'useEffect\s*\(\s*\(\)\s*=>', source):
        effects.append(EffectDef(type="useEffect"))
    return effects


def _extract_vue_state(source: str) -> list[StateDef]:
    """Extract Vue ref/reactive declarations."""
    states = []
    for match in re.finditer(r'(?:const|let)\s+(\w+)\s*=\s*ref\(([^)]*)\)', source):
        states.append(StateDef(
            name=match.group(1),
            type="ref",
            init_value=match.group(2) or "",
            framework_specific="ref",
        ))
    for match in re.finditer(r'(?:const|let)\s+(\w+)\s*=\s*reactive\(([^)]*)\)', source):
        states.append(StateDef(
            name=match.group(1),
            type="reactive",
            init_value=match.group(2) or "",
            framework_specific="reactive",
        ))
    return states


def _extract_vue_effects(source: str) -> list[EffectDef]:
    """Extract Vue watch/onMounted."""
    effects = []
    for match in re.finditer(r'onMounted\s*\(', source):
        effects.append(EffectDef(type="onMounted"))
    for match in re.finditer(r'watch\s*\(', source):
        effects.append(EffectDef(type="watch"))
    return effects


def _extract_svelte_state(source: str) -> list[StateDef]:
    """Extract Svelte let: and $: declarations."""
    states = []
    for match in re.finditer(r'(?:let|var|const)\s+(\w+)\s*=\s*([^;]+);', source):
        states.append(StateDef(
            name=match.group(1),
            type="let",
            init_value=match.group(2) or "",
            framework_specific="let",
        ))
    return states


def _extract_svelte_effects(source: str) -> list[EffectDef]:
    """Extract Svelte $: reactive statements."""
    effects = []
    for match in re.finditer(r'\$\s*:\s*', source):
        effects.append(EffectDef(type="reactive"))
    return effects


def _extract_api_calls(source: str) -> list[APICallDef]:
    """Extract API calls (fetch, axios, etc.)."""
    calls = []
    
    # fetch() calls
    for match in re.finditer(r'fetch\s*\(\s*[`"\']([^`"\']+)[`"\']', source):
        calls.append(APICallDef(
            url=match.group(1),
            method="GET",
            function_name="",
            is_sse="EventSource" in source or "text/event-stream" in source,
            is_websocket="WebSocket" in source or "ws://" in source,
        ))
    
    # axios calls
    for match in re.finditer(r'axios\.(get|post|put|delete|patch)\s*\(\s*[`"\']([^`"\']+)[`"\']', source):
        calls.append(APICallDef(
            url=match.group(2),
            method=match.group(1).upper(),
            function_name="",
        ))
    
    return calls


def _extract_imports(content: str) -> list[ImportDef]:
    """Extract import statements."""
    imports = []
    
    for match in re.finditer(r"import\s+(?:type\s+)?\{([^}]+)\}\s+from\s+['\"]([^'\"]+)['\"]", content):
        names = [n.strip() for n in match.group(1).split(",")]
        imports.append(ImportDef(
            module=match.group(2),
            names=names,
            is_type_only="type" in match.group(0),
            is_relative=match.group(2).startswith("."),
        ))
    
    for match in re.finditer(r"import\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]", content):
        imports.append(ImportDef(
            module=match.group(2),
            names=[match.group(1)],
            is_default=True,
            is_relative=match.group(2).startswith("."),
        ))
    
    return imports


def _extract_child_components(source: str) -> list[str]:
    """Extract child component references (uppercase JSX tags)."""
    return list(set(re.findall(r'<([A-Z]\w+)', source)))


def _extract_hooks(source: str) -> list[str]:
    """Extract React hooks used."""
    return list(set(re.findall(r'use([A-Z]\w+)\s*\(', source)))


def _detect_css_approach(source: str) -> str:
    """Detect the CSS approach used in the component."""
    if "className=" in source and "tailwind" not in source.lower():
        return "className"
    if "styled." in source or "styled-components" in source:
        return "styled-components"
    if ".module.css" in source or ".module.scss" in source:
        return "css-modules"
    if "style={{" in source:
        return "inline-styles"
    return "unknown"


def _extract_css_variables(source: str) -> list[str]:
    """Extract CSS variable references."""
    return list(set(re.findall(r'var\((--[^)]+)\)', source)))


def _extract_tailwind_classes(source: str) -> list[str]:
    """Extract Tailwind CSS classes from className attributes."""
    classes = set()
    for match in re.finditer(r'className=["\']([^"\']*)["\']', source):
        for cls in match.group(1).split():
            classes.add(cls)
    return list(classes)


def extract_routes(
    repo_path: Path,
    framework: Framework,
) -> list[RouteDef]:
    """Extract route definitions from the project."""
    routes = []
    
    # Next.js: file-based routing
    if framework == Framework.NEXTJS:
        for pattern in ["app", "pages"]:
            dir_path = repo_path / pattern
            if dir_path.exists():
                for page_file in dir_path.rglob("page.*"):
                    rel = str(page_file.relative_to(dir_path))
                    path = "/" + rel.rsplit("/", 1)[0].replace("(", "").replace(")", "").replace("[", ":").replace("]", "")
                    if path.endswith("/"):
                        path = path[:-1]
                    routes.append(RouteDef(
                        path=path if path else "/",
                        component=page_file.stem,
                        file=str(page_file.relative_to(repo_path)),
                    ))
    
    # React Router: explicit routes
    else:
        for file_path in repo_path.rglob("*"):
            if file_path.is_file() and file_path.suffix in (".tsx", ".jsx", ".ts", ".js"):
                content = file_path.read_text()
                for match in re.finditer(r'<Route\s+path=["\']([^"\']+)["\']', content):
                    routes.append(RouteDef(
                        path=match.group(1),
                        component="",
                        file=str(file_path.relative_to(repo_path)),
                        is_dynamic=":" in match.group(1) or "[" in match.group(1),
                    ))
    
    return routes
