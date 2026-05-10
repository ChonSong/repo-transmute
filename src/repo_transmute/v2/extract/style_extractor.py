"""Style system extraction — CSS variables, Tailwind config, design tokens."""

from __future__ import annotations

import json
import re
from pathlib import Path

from repo_transmute.v2.models import StyleSystem, ThemeDef, StyleApproach


def extract_style_system(repo_path: Path) -> StyleSystem:
    """Extract the complete style system from a project."""
    system = StyleSystem()
    
    # Find CSS files
    css_files = list(repo_path.rglob("*.css")) + \
                list(repo_path.rglob("*.scss")) + \
                list(repo_path.rglob("*.sass"))
    system.css_files = [str(f.relative_to(repo_path)) for f in css_files]
    
    # Extract CSS variables
    for css_file in css_files:
        content = css_file.read_text()
        # Extract :root variables
        root_match = re.findall(r'--([\w-]+)\s*:\s*([^;]+);', content)
        for name, value in root_match:
            system.css_variables[f"--{name}"] = value.strip()
    
    # Extract Tailwind config
    tailwind_config = _find_tailwind_config(repo_path)
    if tailwind_config:
        system.tailwind_config = tailwind_config
    
    # Extract themes
    system.themes = _extract_themes(repo_path)
    
    # Determine approach
    system.approach = _determine_style_approach(repo_path, system)
    
    # Extract design tokens
    system.design_tokens = _extract_design_tokens(system)
    
    return system


def _find_tailwind_config(repo_path: Path) -> dict | None:
    """Find and parse Tailwind configuration."""
    for pattern in ["tailwind.config.js", "tailwind.config.ts", "tailwind.config.cjs"]:
        config_path = repo_path / pattern
        if config_path.exists():
            try:
                # Simple regex extraction of theme colors
                content = config_path.read_text()
                colors_match = re.findall(r'["\'](\w+)["\']\s*:\s*["\']([^"\']+)["\']', content)
                if colors_match:
                    return {"colors": dict(colors_match)}
            except Exception:
                pass
    return None


def _extract_themes(repo_path: Path) -> list[ThemeDef]:
    """Extract theme definitions from CSS/JS files."""
    themes = []
    
    for css_file in repo_path.rglob("*.css"):
        content = css_file.read_text()
        
        # Look for theme definitions via data-theme attributes
        theme_matches = re.finditer(
            r'\[data-theme\s*=\s*["\'](\w+)["\']\]\s*{([^}]+)}',
            content,
            re.DOTALL,
        )
        for match in theme_matches:
            theme_name = match.group(1)
            vars_block = match.group(2)
            colors = {}
            for var_match in re.finditer(r'--([\w-]+)\s*:\s*(#[0-9a-fA-F]+|[^;]+);', vars_block):
                colors[var_match.group(1)] = var_match.group(2).strip()
            
            themes.append(ThemeDef(
                name=theme_name,
                is_dark="dark" in theme_name.lower(),
                colors=colors,
                css_variables={f"--{k}": v for k, v in colors.items()},
            ))
    
    return themes


def _determine_style_approach(repo_path: Path, system: StyleSystem) -> StyleApproach:
    """Determine the primary style approach."""
    # Check for Tailwind
    if system.tailwind_config or any("tailwind" in f for f in system.css_files):
        return StyleApproach.TAILWIND
    
    # Check for CSS Modules
    if any(".module.css" in f or ".module.scss" in f for f in system.css_files):
        return StyleApproach.CSS_MODULES
    
    # Check for styled-components
    for ts_file in repo_path.rglob("*.tsx"):
        content = ts_file.read_text()
        if "styled-components" in content or "styled." in content:
            return StyleApproach.STYLED_COMPONENTS
    
    # Check for CSS variables
    if system.css_variables:
        return StyleApproach.CSS_VARIABLES
    
    return StyleApproach.UNKNOWN


def _extract_design_tokens(system: StyleSystem) -> dict:
    """Extract design tokens from the style system."""
    tokens = {}
    
    # Colors from CSS variables
    colors = {}
    for var_name, value in system.css_variables.items():
        if "color" in var_name.lower() or value.startswith("#"):
            colors[var_name] = value
    if colors:
        tokens["colors"] = colors
    
    # Tailwind theme config
    if system.tailwind_config.get("colors"):
        tokens["tailwind_colors"] = system.tailwind_config["colors"]
    
    return tokens
