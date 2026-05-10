"""Style mapper — cross-stack style system mapping."""

from __future__ import annotations

from repo_transmute.v2.models import StyleSystem, StyleApproach


def map_styles(
    source_system: StyleSystem,
    target_approach: StyleApproach,
) -> dict:
    """Map source styles to target style approach.
    
    Generates a mapping that can be used during migration:
    - CSS variables → Tailwind classes or target CSS variables
    - Tailwind classes → target equivalents
    - Color palette mapping
    
    Returns:
        Dict with mapping rules
    """
    mapping = {
        "source_approach": source_system.approach.value,
        "target_approach": target_approach.value,
        "color_mapping": {},
        "variable_mapping": {},
        "utility_mapping": {},
    }
    
    # Map CSS variables
    for var_name, value in source_system.css_variables.items():
        if target_approach == StyleApproach.TAILWIND:
            # Map to Tailwind custom properties or theme extension
            mapping["variable_mapping"][var_name] = f"theme('{var_name}')"
        elif target_approach == StyleApproach.CSS_VARIABLES:
            # Keep as-is
            mapping["variable_mapping"][var_name] = var_name
        else:
            mapping["variable_mapping"][var_name] = value
    
    # Map Tailwind classes
    if source_system.approach == StyleApproach.TAILWIND and target_approach != StyleApproach.TAILWIND:
        # Map Tailwind utilities to target equivalents
        mapping["utility_mapping"] = {
            "flex": "display: flex",
            "items-center": "align-items: center",
            "justify-center": "justify-content: center",
            "p-4": "padding: 1rem",
            "m-4": "margin: 1rem",
            "text-lg": "font-size: 1.125rem",
            "font-bold": "font-weight: 700",
            "text-gray-500": "color: #6B7280",
            "bg-white": "background-color: #FFFFFF",
            "rounded-lg": "border-radius: 0.5rem",
            "shadow-md": "box-shadow: 0 4px 6px rgba(0,0,0,0.1)",
        }
    
    # Color mapping
    for var_name, value in source_system.css_variables.items():
        if value.startswith("#") or "color" in var_name.lower():
            mapping["color_mapping"][var_name] = value
    
    return mapping
