"""Vision-based layout analysis — detects components, structure, and visual elements.
Uses the hermes vision_analyze tool to perform deep analysis of UI screenshots.
"""

from __future__ import annotations

from pathlib import Path


def analyze_layout(screenshot_path: str) -> dict:
    """Analyze a screenshot to identify layout structure and components.

    Returns:
        Dict with layout analysis including detected regions, components, colors, etc.
    """
    from hermes_tools import vision_analyze

    path = Path(screenshot_path)
    if not path.exists():
        return {
            "layout_type": "error",
            "regions": [],
            "components": [],
            "colors": {},
            "typography": {},
            "spacing": {},
            "error": f"File not found: {screenshot_path}",
        }

    prompt = """Analyze this UI screenshot in detail. For each section, describe:

1. **Layout type**: sidebar, grid, stack, bento, single-column, etc.
2. **Regions**: List the distinct UI regions (header, sidebar, main content, right panel, footer, etc.)
   with their approximate position (top/middle/bottom, left/center/right)
3. **Components**: Identify individual UI components (buttons, cards, inputs, navigation items, etc.)
4. **Colors**: Describe the dominant color palette — exact hex values for backgrounds, text, accents
5. **Typography**: Note font sizes, weights, any distinctive text styles
6. **Spacing**: Describe padding, margins, gaps between elements
7. **Visual effects**: Any shadows, gradients, glassmorphism, borders, rounded corners

Be specific and precise. Use exact hex codes where possible."""

    try:
        description = vision_analyze(str(path), prompt)
        return _parse_layout_description(description, screenshot_path)
    except Exception as e:
        return {
            "layout_type": "error",
            "regions": [],
            "components": [],
            "colors": {},
            "typography": {},
            "spacing": {},
            "error": str(e),
            "raw_description": str(e),
        }


def _parse_layout_description(description: str, screenshot_path: str) -> dict:
    """Parse the vision model output into structured fields."""
    result = {
        "screenshot": screenshot_path,
        "layout_type": "unknown",
        "regions": [],
        "components": [],
        "colors": {},
        "typography": {},
        "spacing": {},
        "raw_description": description,
    }

    desc_lower = description.lower()

    # Detect layout type
    if "sidebar" in desc_lower and "main" in desc_lower:
        result["layout_type"] = "sidebar+main"
    elif "bento" in desc_lower or "grid" in desc_lower:
        result["layout_type"] = "bento/grid"
    elif "stack" in desc_lower or "vertical" in desc_lower:
        result["layout_type"] = "stacked"
    elif "single" in desc_lower and "column" in desc_lower:
        result["layout_type"] = "single-column"
    else:
        result["layout_type"] = "mixed"

    # Extract hex colors mentioned
    import re

    hex_matches = re.findall(r"#(?:[0-9a-fA-F]{3}){1,2}", description)
    result["colors"]["hex_values"] = list(set(hex_matches))

    # Extract regions mentioned
    region_keywords = ["header", "top bar", "sidebar", "left panel", "right panel", "main content", "center", "footer", "bottom bar", "dock", "navigation"]
    for kw in region_keywords:
        if kw in desc_lower:
            result["regions"].append(kw)

    return result


def match_components(
    source_screenshot: str,
    target_screenshot: str,
) -> dict:
    """Match components between source and target screenshots.

    Returns:
        Dict mapping source components to target components with similarity scores.
    """
    from hermes_tools import vision_analyze

    prompt = """Compare these two UI screenshots (left=source, right=target).

For each region/component in the source screenshot, identify:
- Is the equivalent present in the target? (yes/no/partially)
- How similar is it? (high/medium/low)
- What's different? (color, size, position, missing elements)

Create a structured mapping: for each source component, note the matching target component
(or "not found" if missing) and rate the similarity.

List specific differences in color, spacing, typography, or layout."""

    try:
        comparison = vision_analyze(
            f"{source_screenshot}+{target_screenshot}",
            prompt,
        )
        return _parse_component_match(comparison, source_screenshot, target_screenshot)
    except Exception as e:
        return {
            "matches": [],
            "unmatched_source": [],
            "unmatched_target": [],
            "error": str(e),
        }


def _parse_component_match(comparison: str, source: str, target: str) -> dict:
    """Parse vision comparison into structured match data."""
    return {
        "source": source,
        "target": target,
        "comparison_text": comparison,
        "matches": [],
        "unmatched_source": [],
        "unmatched_target": [],
    }