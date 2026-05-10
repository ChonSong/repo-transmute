"""Screenshot pipeline — Playwright-based page and component capture."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from datetime import datetime

from repo_transmute.v2.models import ScreenshotDef


def capture_page_screenshots(
    url: str,
    output_dir: Path,
    viewport: tuple[int, int] = (1920, 1080),
    wait_for: str = "networkidle",
) -> list[ScreenshotDef]:
    """Capture screenshots of a single page at different states.
    
    Uses Playwright to load the page and take full-page screenshots.
    Also captures component-level screenshots if component selectors are provided.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Write a temporary Playwright script
    script = f"""
const {{ chromium }} = require('playwright');

(async () => {{
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({{ width: {viewport[0]}, height: {viewport[1]} }});
  
  try {{
    await page.goto('{url}', {{ waitUntil: '{wait_for}', timeout: 30000 }});
    
    // Wait for fonts
    await page.evaluate(() => document.fonts.ready);
    
    // Full page screenshot
    await page.screenshot({{
      path: '{output_dir}/fullpage_{timestamp}.png',
      fullPage: true,
    }});
    
    // Viewport screenshot
    await page.screenshot({{
      path: '{output_dir}/viewport_{timestamp}.png',
      fullPage: false,
    }});
    
    // Get all component bounding boxes
    const components = await page.evaluate(() => {{
      const results = [];
      // Find elements with common component attributes
      const selectors = [
        '[data-component]', '[data-testid]', '[role]',
        'header', 'nav', 'main', 'footer', 'aside',
        '.component', '.widget', '.card', '.panel',
      ];
      
      for (const sel of selectors) {{
        const elements = document.querySelectorAll(sel);
        for (const el of elements) {{
          const rect = el.getBoundingClientRect();
          if (rect.width > 50 && rect.height > 30) {{
            results.push({{
              selector: sel,
              tag: el.tagName.toLowerCase(),
              x: Math.round(rect.x),
              y: Math.round(rect.y),
              width: Math.round(rect.width),
              height: Math.round(rect.height),
              text: (el.textContent || '').substring(0, 50),
            }});
          }}
        }}
      }}
      
      // Deduplicate overlapping elements
      return results.slice(0, 50); // Cap at 50 components
    }});
    
    console.log(JSON.stringify(components));
    
    // Screenshot each component
    for (const comp of components) {{
      try {{
        const el = document.querySelector(comp.selector);
        if (el) {{
          await el.screenshot({{
            path: `{output_dir}/comp_${{comp.tag}}_${{comp.x}}_${{comp.y}}_${{timestamp}}.png`,
          }});
        }}
      }} catch (e) {{
        // Skip elements that can't be screenshotted individually
      }}
    }}
  }} catch (e) {{
    console.error('Error:', e.message);
  }} finally {{
    await browser.close();
  }}
}})();
"""
    
    script_path = output_dir / f"_capture_{timestamp}.js"
    script_path.write_text(script)
    
    try:
        result = subprocess.run(
            ["node", str(script_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        screenshots = []
        
        # Parse component data from stdout
        for line in result.stdout.strip().split("\n"):
            if line.startswith("["):
                try:
                    components = json.loads(line)
                    for comp in components:
                        screenshots.append(ScreenshotDef(
                            page_url=url,
                            component_name=f"{comp['tag']}_{comp['x']}_{comp['y']}",
                            viewport=viewport,
                            full_page=False,
                            file_path=f"{output_dir}/comp_{comp['tag']}_{comp['x']}_{comp['y']}_{timestamp}.png",
                            timestamp=timestamp,
                            component_bounds={
                                "x": comp["x"],
                                "y": comp["y"],
                                "width": comp["width"],
                                "height": comp["height"],
                            },
                        ))
                except json.JSONDecodeError:
                    pass
        
        # Add full-page screenshots
        for name in ["fullpage", "viewport"]:
            path = output_dir / f"{name}_{timestamp}.png"
            if path.exists():
                screenshots.insert(0, ScreenshotDef(
                    page_url=url,
                    component_name=f"{name}_page",
                    viewport=viewport,
                    full_page=(name == "fullpage"),
                    file_path=str(path),
                    timestamp=timestamp,
                ))
        
        return screenshots
        
    finally:
        # Clean up temp script
        if script_path.exists():
            script_path.unlink()


def capture_component_screenshot(
    url: str,
    selector: str,
    output_dir: Path,
    component_name: str = "",
) -> ScreenshotDef | None:
    """Screenshot a specific component by CSS selector."""
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = component_name or selector.replace("[", "").replace("]", "").replace("=", "_").replace('"', "")
    
    script = f"""
const {{ chromium }} = require('playwright');

(async () => {{
  const browser = await chromium.launch();
  const page = await browser.newPage();
  
  try {{
    await page.goto('{url}', {{ waitUntil: 'networkidle', timeout: 30000 }});
    await page.evaluate(() => document.fonts.ready);
    
    const el = await page.$('{selector}');
    if (el) {{
      await el.screenshot({{
        path: '{output_dir}/{name}_{timestamp}.png',
      }});
      console.log('OK');
    }} else {{
      console.log('NOT_FOUND');
    }}
  }} catch (e) {{
    console.error('Error:', e.message);
  }} finally {{
    await browser.close();
  }}
}})();
"""
    
    script_path = output_dir / f"_comp_capture_{timestamp}.js"
    script_path.write_text(script)
    
    try:
        result = subprocess.run(
            ["node", str(script_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        path = output_dir / f"{name}_{timestamp}.png"
        if path.exists() and "OK" in result.stdout:
            return ScreenshotDef(
                page_url=url,
                component_name=name,
                viewport=(1920, 1080),
                full_page=False,
                file_path=str(path),
                timestamp=timestamp,
            )
        return None
        
    finally:
        if script_path.exists():
            script_path.unlink()


def check_playwright_installed() -> bool:
    """Check if Playwright is installed."""
    try:
        result = subprocess.run(
            ["npx", "playwright", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def install_playwright() -> bool:
    """Install Playwright with Chromium browser."""
    try:
        subprocess.run(
            ["npm", "install", "playwright"],
            capture_output=True,
            check=True,
            timeout=120,
        )
        subprocess.run(
            ["npx", "playwright", "install", "chromium"],
            capture_output=True,
            check=True,
            timeout=120,
        )
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
