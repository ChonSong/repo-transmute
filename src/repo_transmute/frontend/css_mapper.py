"""CSS/theme extraction and mapping for frontend migration.

Handles:
- CSS variable extraction from stylesheets
- Theme system detection (data-theme, class-based, JS objects)
- Tailwind class mapping between projects
- Theme variable compatibility analysis
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CSSVarDef:
    """A CSS custom property definition."""
    name: str  # --theme-bg, etc.
    value: str  # #0a0e1a, rgba(...), etc.
    scope: str  # :root, [data-theme='xxx'], etc.
    file: str = ""
    line: int = 0


@dataclass
class ThemeDef:
    """A complete theme definition."""
    name: str  # e.g., "claude-nous", "matrix"
    is_dark: bool = True
    variables: dict[str, str] = field(default_factory=dict)
    file: str = ""
    extends: str = ""  # parent theme name if any


@dataclass
class TailwindTheme:
    """Tailwind theme configuration extracted from CSS/JS."""
    extends: str = ""  # 'default', 'light', 'dark'
    colors: dict[str, Any] = field(default_factory=dict)
    font_families: dict[str, str] = field(default_factory=dict)
    extend_colors: dict[str, Any] = field(default_factory=dict)


@dataclass
class CSSThemeSystem:
    """Complete theme system extracted from a project."""
    theme_approach: str = ""  # css-vars, tailwind, js-object, styled-components
    themes: list[ThemeDef] = field(default_factory=list)
    css_variables: list[CSSVarDef] = field(default_factory=list)
    tailwind_config: TailwindTheme | None = None
    font_families: list[str] = field(default_factory=list)
    keyframe_animations: list[str] = field(default_factory=list)
    global_utilities: list[str] = field(default_factory=list)  # .theme-bg, .kpi-card, etc.


def extract_css_theme_system(repo_path: Path) -> CSSThemeSystem:
    """Extract the complete theme system from a project."""
    system = CSSThemeSystem()
    
    for css_file in repo_path.rglob('*.css'):
        if 'node_modules' in str(css_file) or 'dist' in str(css_file):
            continue
        
        content = css_file.read_text()
        rel_path = str(css_file.relative_to(repo_path))
        
        # Detect approach
        if '[data-theme' in content or '[data-theme=' in content:
            system.theme_approach = 'css-vars'
        elif '@layer' in content or 'tailwind' in content.lower():
            if not system.theme_approach:
                system.theme_approach = 'tailwind'
        
        # Extract CSS variables
        _extract_css_vars(content, rel_path, system)
        
        # Extract theme definitions
        _extract_themes(content, rel_path, system)
        
        # Extract keyframes
        _extract_keyframes(content, system)
        
        # Extract global utility classes
        _extract_utility_classes(content, system)
        
        # Extract font families
        _extract_fonts(content, system)
    
    # Check for Tailwind config
    for config_file in repo_path.rglob('tailwind.config.*'):
        if 'node_modules' in str(config_file):
            continue
        content = config_file.read_text()
        system.tailwind_config = _extract_tailwind_config(content)
    
    # Also check for Tailwind v4 config in CSS
    if not system.tailwind_config:
        for css_file in repo_path.rglob('*.css'):
            if 'node_modules' in str(css_file):
                continue
            content = css_file.read_text()
            if '@theme' in content or 'tailwindcss' in content:
                system.tailwind_config = _extract_tailwind_v4_config(content)
                break
    
    return system


def _extract_css_vars(content: str, file: str, system: CSSThemeSystem):
    """Extract CSS custom property definitions."""
    # Pattern: --var-name: value;
    var_pattern = re.compile(r'([\w-]+)\s*:\s*([^;]+);')
    
    # Track current scope
    lines = content.splitlines()
    current_scope = ':root'
    brace_depth = 0
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # Track scope changes
        if stripped.startswith(('[data-theme', '[data-', '.dark', '.light', ':root')):
            if '[' in stripped:
                match = re.match(r'(\[data-theme[^\]]*\]|\[data-[^\]]*\]|\.\w+|:\w+)', stripped)
                if match:
                    current_scope = match.group(1)
            elif stripped.startswith(':root'):
                current_scope = ':root'
            elif stripped.startswith('.'):
                current_scope = stripped.split()[0]
            brace_depth += 1
        
        if '{' in stripped and not stripped.endswith('{'):
            brace_depth += 1
        if '}' in stripped:
            brace_depth = max(0, brace_depth - 1)
            if brace_depth == 0:
                current_scope = ':root'
        
        # Extract variable
        var_match = var_pattern.search(stripped)
        if var_match and var_match.group(1).startswith('--'):
            system.css_variables.append(CSSVarDef(
                name=var_match.group(1),
                value=var_match.group(2).strip(),
                scope=current_scope,
                file=file,
                line=i + 1,
            ))


def _extract_themes(content: str, file: str, system: CSSThemeSystem):
    """Extract theme definitions from [data-theme='xxx'] blocks."""
    # Pattern: [data-theme='name'] { ... }
    theme_pattern = re.compile(
        r"\[data-theme='([\w-]+)'\]\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}",
        re.DOTALL,
    )
    
    for m in theme_pattern.finditer(content):
        theme_name = m.group(1)
        theme_body = m.group(2)
        
        variables = {}
        for var_match in re.finditer(r'(--[\w-]+)\s*:\s*([^;]+);', theme_body):
            variables[var_match.group(1)] = var_match.group(2).strip()
        
        is_dark = 'light' not in theme_name.lower() and not theme_name.endswith('-light')
        
        system.themes.append(ThemeDef(
            name=theme_name,
            is_dark=is_dark,
            variables=variables,
            file=file,
        ))


def _extract_keyframes(content: str, system: CSSThemeSystem):
    """Extract @keyframes animation names."""
    for m in re.finditer(r'@keyframes\s+([\w-]+)', content):
        system.keyframe_animations.append(m.group(1))


def _extract_utility_classes(content: str, system: CSSThemeSystem):
    """Extract global utility class definitions."""
    for m in re.finditer(r'^\.([\w-]+)\s*\{', content, re.MULTILINE):
        class_name = m.group(1)
        # Skip component-specific classes (camelCase, BEM with multiple dashes)
        if not any(c.isupper() for c in class_name) and '-' not in class_name[:15]:
            system.global_utilities.append(class_name)


def _extract_fonts(content: str, system: CSSThemeSystem):
    """Extract font family definitions."""
    for m in re.finditer(r"font-family:\s*([^;]+);", content):
        fonts = m.group(1).strip()
        if fonts not in system.font_families:
            system.font_families.append(fonts)
    
    # Also check for @import of Google Fonts
    for m in re.finditer(r"@import\s+url\('([^']*fonts[^']*)'\)", content):
        system.font_families.append(f"Google Fonts: {m.group(1)}")


def _extract_tailwind_config(content: str) -> TailwindTheme | None:
    """Extract Tailwind v3 config from JS/TS file."""
    try:
        import ast
        # Try to parse as Python... no, it's JS. Use regex.
        pass
    except ImportError:
        pass
    
    # Regex extraction (simplified)
    config = TailwindTheme()
    
    # Look for colors definition
    color_pattern = re.compile(r'colors:\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}', re.DOTALL)
    m = color_pattern.search(content)
    if m:
        colors_body = m.group(1)
        # Parse simple color definitions
        for line in colors_body.splitlines():
            line = line.strip()
            if ':' in line and not line.startswith('//'):
                parts = line.split(':', 1)
                if len(parts) == 2:
                    key = parts[0].strip().strip("'\"")
                    val = parts[1].strip().rstrip(',').strip("'\"")
                    if key and val:
                        config.colors[key] = val
    
    return config if config.colors else None


def _extract_tailwind_v4_config(content: str) -> TailwindTheme | None:
    """Extract Tailwind v4 theme config from CSS @theme block."""
    config = TailwindTheme()
    
    # Look for @theme { ... } blocks
    theme_pattern = re.compile(r'@theme\s*\{([^}]+)\}', re.DOTALL)
    m = theme_pattern.search(content)
    if m:
        theme_body = m.group(1)
        for line in theme_body.splitlines():
            line = line.strip()
            if '--color-' in line and ':' in line:
                match = re.match(r'--color-([\w-]+)\s*:\s*([^;]+);', line)
                if match:
                    config.extend_colors[match.group(1)] = match.group(2).strip()
    
    return config if config.extend_colors else None


def map_theme_compatibility(
    source_system: CSSThemeSystem,
    target_system: CSSThemeSystem,
) -> dict[str, Any]:
    """Analyze theme compatibility between source and target projects.
    
    Returns a mapping report showing which variables match, which need
    conversion, and which are missing.
    """
    # Build variable maps
    source_vars = {}
    for var in source_system.css_variables:
        if var.name not in source_vars:
            source_vars[var.name] = []
        source_vars[var.name].append(var)
    
    target_vars = set()
    for var in target_system.css_variables:
        target_vars.add(var.name)
    
    # Also check source themes
    source_theme_vars = {}
    for theme in source_system.themes:
        source_theme_vars[theme.name] = set(theme.variables.keys())
    
    target_theme_vars = {}
    for theme in target_system.themes:
        target_theme_vars[theme.name] = set(theme.variables.keys())
    
    # Analysis
    common_vars = set(source_vars.keys()) & target_vars
    source_only = set(source_vars.keys()) - target_vars
    target_only = target_vars - set(source_vars.keys())
    
    # Theme matching
    matched_themes = []
    for src_theme in source_system.themes:
        for tgt_theme in target_system.themes:
            if src_theme.name == tgt_theme.name:
                matched_themes.append({
                    'name': src_theme.name,
                    'source_vars': len(src_theme.variables),
                    'target_vars': len(tgt_theme.variables),
                    'common': len(set(src_theme.variables.keys()) & set(tgt_theme.variables.keys())),
                })
    
    return {
        'compatibility_score': len(common_vars) / max(len(source_vars), 1),
        'common_variables': sorted(common_vars),
        'source_only_variables': sorted(source_only),
        'target_only_variables': sorted(target_only),
        'theme_matches': matched_themes,
        'source_theme_count': len(source_system.themes),
        'target_theme_count': len(target_system.themes),
        'source_approach': source_system.theme_approach,
        'target_approach': target_system.theme_approach,
        'recommendation': _generate_recommendation(
            source_system, target_system,
            common_vars, source_only, target_only,
        ),
    }


def _generate_recommendation(
    source: CSSThemeSystem,
    target: CSSThemeSystem,
    common: set,
    source_only: set,
    target_only: set,
) -> str:
    """Generate a migration recommendation."""
    if source.theme_approach == target.theme_approach:
        if len(common) > len(source_only):
            return (
                f"Both projects use {source.theme_approach} with {len(common)} common variables. "
                f"Migration is straightforward — copy source themes and add {len(source_only)} missing variables."
            )
        else:
            return (
                f"Both projects use {source.theme_approach} but have different variable sets. "
                f"Need to create mapping for {len(source_only)} source variables."
            )
    else:
        return (
            f"Source uses {source.theme_approach}, target uses {target.theme_approach}. "
            f"Theme system needs conversion — extract source variable semantics and map to target format."
        )


def extract_api_url_mappings(source_repo: Path, target_repo: Path | None = None) -> dict[str, Any]:
    """Extract API URL patterns from source project and optionally map to target."""
    source_urls = set()
    source_patterns = []
    
    for ext in ('.tsx', '.jsx', '.ts', '.js'):
        for file_path in source_repo.rglob(f'*{ext}'):
            if 'node_modules' in str(file_path) or 'dist' in str(file_path):
                continue
            
            content = file_path.read_text()
            rel_path = str(file_path.relative_to(source_repo))
            
            # find all URL strings that look like API paths
            for m in re.finditer(r'[`\'"](/api/[^`\'"]+)[`\'"]', content):
                url = m.group(1)
                source_urls.add(url)
                source_patterns.append({
                    'url': url,
                    'file': rel_path,
                })
    
    # Group by base path
    url_groups = {}
    for url in sorted(source_urls):
        parts = url.split('/')
        base = '/'.join(parts[:3]) if len(parts) >= 3 else url
        if base not in url_groups:
            url_groups[base] = []
        url_groups[base].append(url)
    
    return {
        'total_unique_urls': len(source_urls),
        'url_groups': url_groups,
        'patterns': source_patterns,
    }
