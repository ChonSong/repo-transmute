"""Compare source and target screenshots."""

from __future__ import annotations

from repo_transmute.v2.models import VisionResult


def compare_screenshots(
    source_path: str,
    target_path: str,
) -> VisionResult:
    """Compare two screenshots and return a vision result.
    
    This will use the vision model to:
    1. Analyze both screenshots for layout, colors, typography, spacing
    2. Compute similarity scores
    3. Identify specific issues
    4. Generate fix suggestions
    """
    return VisionResult(
        source_screenshot=source_path,
        target_screenshot=target_path,
        overall_score=0.0,
        issues=[],
        suggestions=[],
    )
