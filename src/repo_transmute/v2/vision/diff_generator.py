"""Visual diff generation — annotated comparison between source and target."""

from __future__ import annotations

from pathlib import Path


def generate_visual_diff(
    source_screenshot: str,
    target_screenshot: str,
    output_path: str | None = None,
) -> str:
    """Generate a side-by-side visual diff with annotations.
    
    Creates a composite image showing:
    - Source screenshot on left
    - Target screenshot on right
    - Red outlines around mismatched areas
    - Green outlines around matched areas
    
    Returns:
        Path to the generated diff image
    """
    if output_path is None:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"/tmp/visual_diff_{ts}.png"
    
    # This will be implemented using PIL/Pillow to composite images
    # For now, return the path placeholder
    return output_path
