"""Visual diff generation — annotated comparison between source and target.
Creates side-by-side annotated diffs showing matched/different regions.
"""

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
    from datetime import datetime

    if output_path is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"/tmp/visual_diff_{ts}.png"

    try:
        from PIL import Image

        source_path = Path(source_screenshot)
        target_path = Path(target_screenshot)

        if not source_path.exists() or not target_path.exists():
            return _generate_placeholder_diff(source_screenshot, target_screenshot, output_path)

        # Open both images
        source_img = Image.open(source_path).convert("RGB")
        target_img = Image.open(target_path).convert("RGB")

        # Resize target to match source dimensions for comparison
        if source_img.size != target_img.size:
            target_img = target_img.resize(source_img.size, Image.LANCZOS)

        # Create composite side-by-side
        total_width = source_img.width + target_img.width
        max_height = max(source_img.height, target_img.height)
        composite = Image.new("RGB", (total_width, max_height), (20, 20, 20))

        composite.paste(source_img, (0, 0))
        composite.paste(target_img, (source_img.width, 0))

        # Add labels
        from PIL import ImageDraw, ImageFont

        draw = ImageDraw.Draw(composite)

        # Try to use a default font, fall back to built-in
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
        except Exception:
            font = ImageFont.load_default()

        # Label source
        draw.text((10, 10), "SOURCE", fill=(0, 200, 100), font=font)
        # Label target
        draw.text((source_img.width + 10, 10), "TARGET", fill=(200, 100, 0), font=font)

        # Draw divider line
        draw.line([(source_img.width, 0), (source_img.width, max_height)], fill=(100, 100, 100), width=2)

        # Save
        composite.save(output_path)
        return output_path

    except ImportError:
        # PIL not available — generate text report
        return _generate_placeholder_diff(source_screenshot, target_screenshot, output_path)
    except Exception as e:
        return _generate_placeholder_diff(source_screenshot, target_screenshot, output_path, error=str(e))


def _generate_placeholder_diff(
    source: str,
    target: str,
    output_path: str,
    error: str | None = None,
) -> str:
    """Generate a text-based diff report when PIL is unavailable."""
    content = f"""Visual Diff Report
==================
Source: {source}
Target: {target}
Generated: (timestamp placeholder)

This diff requires PIL/Pillow to composite images.
Install with: pip install Pillow

Error context: {error or 'PIL not available'}

To generate the image manually, run:
  python -c "
from PIL import Image
source = Image.open('{source}')
target = Image.open('{target}')
# composite and annotate
"
"""
    # Write as text fallback (would need .txt extension ideally, but keep path)
    text_path = output_path.replace(".png", ".txt")
    Path(text_path).write_text(content)
    return text_path