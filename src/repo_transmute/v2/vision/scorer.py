"""Visual similarity scoring between source and target screenshots.
Uses the hermes vision_analyze tool for perception-aligned comparison.
"""

from __future__ import annotations

from pathlib import Path

from repo_transmute.v2.models import VisionResult


def score_similarity(
    source_screenshot: str,
    target_screenshot: str,
    component_name: str = "",
) -> VisionResult:
    """Score the visual similarity between source and target screenshots.

    Uses the vision model to compare screenshots and generate a score.
    The scoring considers:
    - Layout structure (regions, positioning)
    - Color palette match
    - Typography (font families, sizes, weights)
    - Spacing (padding, margins, gaps)
    - Component presence and arrangement

    Returns:
        VisionResult with scores and issues

    Note: This function calls vision_analyze via hermes agent context.
    When called from the v2 CLI, use the agent's vision_analyze tool directly.
    When called programmatically, ensure hermes_tools.vision_analyze is available.
    """
    source_path = Path(source_screenshot)
    target_path = Path(target_screenshot)

    if not source_path.exists():
        return VisionResult(
            source_screenshot=source_screenshot,
            target_screenshot=target_screenshot,
            overall_score=0.0,
            issues=[f"Source screenshot not found: {source_screenshot}"],
            suggestions=[],
        )

    if not target_path.exists():
        return VisionResult(
            source_screenshot=source_screenshot,
            target_screenshot=target_screenshot,
            overall_score=0.0,
            issues=[f"Target screenshot not found: {target_screenshot}"],
            suggestions=[],
        )

    # Try to use hermes_tools if available (agent runtime)
    try:
        from hermes_tools import vision_analyze as va
        _use_vision_tool = va
    except ImportError:
        _use_vision_tool = None

    if _use_vision_tool is None:
        # Not in hermes runtime — return a placeholder requiring agent context
        return VisionResult(
            source_screenshot=source_screenshot,
            target_screenshot=target_screenshot,
            overall_score=0.0,
            issues=["vision_analyze not available — run via 'v2 qa' CLI command from hermes agent"],
            suggestions=["Run: v2 qa <reference> --live-url <url>"],
            layout_match=False,
            color_match=False,
            typography_match=False,
            spacing_match=False,
        )

    # Vision model comparison with structured output
    prompt = f"""Compare these two UI screenshots. Left is the SOURCE (reference). Right is the TARGET (current state).

{f"Focus especially on: {component_name}" if component_name else ""}

Score each dimension 0-10 and provide specific findings:

**COLOR MATCH**: Do the colors match? List specific hex differences.
  - Source dominant colors: [extract from left image]
  - Target dominant colors: [extract from right image]
  - Exact mismatches with hex values

**LAYOUT MATCH**: Does the layout structure match? Are regions in the same positions?
  - Matching regions: [list]
  - Different/missing regions: [list]

**SPACING MATCH**: Are gaps, padding, and margins consistent?
  - Specific spacing differences: [list]

**TYPOGRAPHY**: Are fonts, sizes, weights visually consistent?
  - Differences observed: [list]

**OVERALL SCORE**: Estimate 0.0-1.0 similarity.

Respond with this exact format:
COLOR_SCORE: <0-10>
COLOR_ISSUES: <list specific hex mismatches>
LAYOUT_SCORE: <0-10>
LAYOUT_ISSUES: <list missing/different regions>
SPACING_SCORE: <0-10>
SPACING_ISSUES: <list spacing differences>
TYPOGRAPHY_SCORE: <0-10>
TYPOGRAPHY_ISSUES: <list font differences>
OVERALL_SCORE: <0.00-1.00>
SUGGESTIONS: <list of specific fixes>"""

    try:
        analysis = _use_vision_tool(f"{source_screenshot},{target_screenshot}", prompt)
        return _parse_vision_result(analysis, source_screenshot, target_screenshot, component_name)
    except Exception as e:
        return VisionResult(
            source_screenshot=source_screenshot,
            target_screenshot=target_screenshot,
            overall_score=0.0,
            issues=[f"Vision analysis failed: {str(e)}"],
            suggestions=[],
            layout_match=False,
            color_match=False,
            typography_match=False,
            spacing_match=False,
        )


def _parse_vision_result(analysis: str, source: str, target: str, component: str) -> VisionResult:
    """Parse the structured vision output into a VisionResult."""
    import re

    lines = analysis.split("\n")
    parsed = {}
    current_key = None

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if ":" in line:
            parts = line.split(":", 1)
            key = parts[0].strip().upper().replace(" ", "_")
            value = parts[1].strip()
            parsed[key] = value
        elif current_key and current_key in parsed:
            parsed[current_key] += " " + line

    # Extract scores
    color_score = float(_extract_value(parsed, "COLOR_SCORE", 5)) / 10.0
    layout_score = float(_extract_value(parsed, "LAYOUT_SCORE", 5)) / 10.0
    spacing_score = float(_extract_value(parsed, "SPACING_SCORE", 5)) / 10.0
    typography_score = float(_extract_value(parsed, "TYPOGRAPHY_SCORE", 5)) / 10.0
    overall = float(_extract_value(parsed, "OVERALL_SCORE", 0.5))

    # Extract issues and suggestions
    color_issues = _extract_value(parsed, "COLOR_ISSUES", "")
    layout_issues = _extract_value(parsed, "LAYOUT_ISSUES", "")
    spacing_issues = _extract_value(parsed, "SPACING_ISSUES", "")
    typography_issues = _extract_value(parsed, "TYPOGRAPHY_ISSUES", "")
    suggestions_text = _extract_value(parsed, "SUGGESTIONS", "")

    issues = []
    for issue in [color_issues, layout_issues, spacing_issues, typography_issues]:
        if issue and issue not in ("N/A", "none", "None", ""):
            # Split on commas or periods
            for part in re.split(r"[,;]\s*|\.\s+(?=[A-Z])", issue):
                part = part.strip()
                if part and len(part) > 3:
                    issues.append(part)

    suggestions = []
    for sug in re.split(r"[,;]\s*|\.\s+(?=[A-Z])", suggestions_text):
        sug = sug.strip()
        if sug and len(sug) > 3:
            suggestions.append(sug)

    # If no issues parsed but we have analysis, extract hex colors mentioned
    if not issues and analysis:
        hexes = re.findall(r"#(?:[0-9a-fA-F]{3}){1,2}", analysis)
        if hexes:
            issues.append(f"Colors detected: {', '.join(set(hexes))}")

    return VisionResult(
        source_screenshot=source,
        target_screenshot=target,
        overall_score=overall,
        component_scores={component: overall} if component else {},
        issues=issues[:20],  # Cap at 20 issues
        suggestions=suggestions[:10],  # Cap at 10 suggestions
        layout_match=layout_score >= 0.7,
        color_match=color_score >= 0.7,
        typography_match=typography_score >= 0.7,
        spacing_match=spacing_score >= 0.7,
    )


def _extract_value(parsed: dict, key: str, default: float | str) -> str:
    """Extract a value from parsed dict, returning default if not found."""
    for k in [key, key.replace(" ", "_")]:
        if k in parsed and parsed[k]:
            return parsed[k]
    return str(default)